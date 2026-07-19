"""``coherence_validator`` — validation worker (``validate_estimate`` only)."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any

from app.config import get_settings
from app.services.agentic.agent_tools import validate_estimate as default_validate_estimate
from app.services.estimation_graph.review_policy import ReviewSignals, review_reasons
from app.services.estimation_graph.state import EstimationState

logger = logging.getLogger(__name__)

ValidateEstimateFn = Callable[[dict[str, Any]], dict[str, Any]]


def build_coherence_validator(
    *,
    validate_estimate_fn: ValidateEstimateFn | None = None,
    confidence_threshold: float | None = None,
) -> Callable[[EstimationState], Awaitable[dict[str, Any]]]:
    """Build a worker that may invoke only ``validate_estimate``."""

    validate = validate_estimate_fn or default_validate_estimate

    async def coherence_validator(state: EstimationState) -> dict[str, Any]:
        threshold = (
            confidence_threshold
            if confidence_threshold is not None
            else get_settings().graph_human_review_confidence_threshold
        )
        estimate = state.get("estimate") or {}
        matches = state.get("budget_matches") or []
        tool_args = _validate_args_from_estimate(estimate, matches)
        tool_result = validate(tool_args)

        no_precedent = _has_no_precedent(estimate, matches, tool_result)
        out_of_range = _has_out_of_range(tool_result)
        confidence = _derive_confidence(
            estimate=estimate,
            matches=matches,
            tool_ok=bool(tool_result.get("ok")),
            no_precedent=no_precedent,
            out_of_range=out_of_range,
        )
        signals = ReviewSignals(
            confidence=confidence,
            out_of_historical_range=out_of_range,
            no_precedent=no_precedent,
        )
        reasons = review_reasons(signals, threshold=threshold)
        validation = {
            **tool_result,
            "out_of_historical_range": out_of_range,
            "no_precedent": no_precedent,
            "review_reasons": reasons,
            "confidence": confidence,
        }

        update: dict[str, Any] = {
            "validation": validation,
            "confidence": confidence,
            "completed_workers": ["coherence_validator"],
            "agent_contributions": [
                {
                    "worker": "coherence_validator",
                    "tool": "validate_estimate",
                    "summary": tool_result.get("summary") or "validation complete",
                }
            ],
        }
        resolution = state.get("human_resolution") or {}
        if isinstance(resolution, dict) and resolution.get("action") == "adjust":
            update["human_adjustment_validated"] = True

        logger.info(
            "graph_coherence_validator_done",
            extra={
                "ok": validation.get("ok"),
                "confidence": confidence,
                "review_reason_count": len(reasons),
                "tool": "validate_estimate",
            },
        )
        return update

    return coherence_validator


def _validate_args_from_estimate(
    estimate: dict[str, Any], matches: list[dict[str, Any]]
) -> dict[str, Any]:
    amounts_by_component: dict[str, list[float]] = {}
    for match in matches:
        if match.get("no_match"):
            continue
        component = str(match.get("component") or "")
        amount = match.get("amount")
        if not component or amount is None:
            continue
        amounts_by_component.setdefault(component, []).append(float(amount))

    # Also index by requirement text-ish names from estimate components.
    components_out: list[dict[str, Any]] = []
    for component in estimate.get("components") or []:
        name = str(component.get("name") or "")
        refs = list(amounts_by_component.get(name, []))
        # Fall back to reference_count evidence without inventing amounts.
        if not refs and component.get("unbudgeted"):
            refs = []
        components_out.append(
            {
                "name": name,
                "estimated_hours": float(component.get("estimated_hours") or 0.0),
                "reference_amounts": refs,
            }
        )
    return {
        "components": components_out,
        "total_hours": float(estimate.get("total_hours") or 0.0),
    }


def _has_no_precedent(
    estimate: dict[str, Any],
    matches: list[dict[str, Any]],
    tool_result: dict[str, Any],
) -> bool:
    if any(match.get("no_match") for match in matches):
        return True
    if any(component.get("unbudgeted") for component in estimate.get("components") or []):
        return True
    issues = " ".join(tool_result.get("issues") or []).lower()
    return "no historical reference" in issues or "unbudgeted" in issues


def _has_out_of_range(tool_result: dict[str, Any]) -> bool:
    issues = " ".join(tool_result.get("issues") or []).lower()
    return "outside the plausible range" in issues or "outside the historical range" in issues


def _derive_confidence(
    *,
    estimate: dict[str, Any],
    matches: list[dict[str, Any]],
    tool_ok: bool,
    no_precedent: bool,
    out_of_range: bool,
) -> float:
    """Deterministic confidence in ``0.0..1.0`` from evidence coverage + tool result."""
    components = estimate.get("components") or []
    if not components:
        return 0.0

    budgeted = sum(1 for component in components if not component.get("unbudgeted"))
    coverage = budgeted / len(components)

    # Prefer real match rows when present.
    real_matches = [match for match in matches if not match.get("no_match")]
    if matches:
        coverage = max(coverage, len(real_matches) / max(len(matches), 1))

    confidence = coverage
    if not tool_ok:
        confidence *= 0.7
    if out_of_range:
        confidence *= 0.7
    if no_precedent:
        confidence *= 0.5
    return round(max(0.0, min(1.0, confidence)), 4)
