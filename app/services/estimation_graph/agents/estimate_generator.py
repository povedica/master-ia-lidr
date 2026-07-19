"""``estimate_generator`` — estimate worker (``calculate_estimate`` only)."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any

from app.services.agentic.agent_tools import calculate_estimate as default_calculate_estimate
from app.services.estimation_graph.state import EstimationState

logger = logging.getLogger(__name__)

CalculateEstimateFn = Callable[[dict[str, Any]], dict[str, Any]]


def build_estimate_generator(
    *,
    calculate_estimate_fn: CalculateEstimateFn | None = None,
) -> Callable[[EstimationState], Awaitable[dict[str, Any]]]:
    """Build a worker that may invoke only ``calculate_estimate``."""

    calculate = calculate_estimate_fn or default_calculate_estimate

    async def estimate_generator(state: EstimationState) -> dict[str, Any]:
        requirements = state.get("requirements") or []
        matches = state.get("budget_matches") or []
        components_args = _map_reference_amounts(requirements, matches)
        estimate = calculate({"components": components_args})

        logger.info(
            "graph_estimate_generator_done",
            extra={
                "component_count": len(estimate.get("components") or []),
                "total_hours": estimate.get("total_hours"),
                "tool": "calculate_estimate",
            },
        )
        return {
            "estimate": estimate,
            "completed_workers": ["estimate_generator"],
            "agent_contributions": [
                {
                    "worker": "estimate_generator",
                    "tool": "calculate_estimate",
                    "summary": estimate.get("summary") or "estimate generated",
                }
            ],
        }

    return estimate_generator


def _map_reference_amounts(
    requirements: list[Any], matches: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Map budget matches to ``calculate_estimate`` component inputs.

    Never invents reference amounts: no-match rows contribute an empty list.
    """
    amounts_by_requirement: dict[str, list[float]] = {}
    for match in matches:
        req_id = str(match.get("requirement_id") or "")
        if not req_id:
            continue
        if match.get("no_match"):
            amounts_by_requirement.setdefault(req_id, [])
            continue
        amount = match.get("amount")
        if amount is None:
            continue
        amounts_by_requirement.setdefault(req_id, []).append(float(amount))

    components: list[dict[str, Any]] = []
    for index, requirement in enumerate(requirements):
        if isinstance(requirement, str):
            req_id = f"req-{index + 1}"
            name = requirement.strip() or req_id
        else:
            req_id = str(requirement.get("id") or f"req-{index + 1}")
            name = str(requirement.get("text") or requirement.get("name") or req_id)
        components.append(
            {
                "name": name,
                "reference_amounts": list(amounts_by_requirement.get(req_id, [])),
            }
        )
    return components
