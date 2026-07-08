"""Deterministic agent tools for Session 12 (calculate + validate).

Flat Responses tool schemas and dispatch are added in a follow-up step.
"""

from __future__ import annotations

import logging
import statistics
from typing import Any

from app.services.agentic.agent_schemas import CalculateEstimateArgs, ValidateEstimateArgs

logger = logging.getLogger(__name__)

# Contingency buffer applied to every component's central estimate.
CONTINGENCY_FACTOR = 0.15


def calculate_estimate(raw_args: dict[str, Any]) -> dict[str, Any]:
    """Deterministically cost the components. No LLM."""
    args = CalculateEstimateArgs.model_validate(raw_args)
    breakdown: list[dict[str, Any]] = []
    total = 0.0
    for component in args.components:
        refs = component.reference_amounts
        if refs:
            central = statistics.median(refs)
            hours = round(central * (1 + CONTINGENCY_FACTOR), 1)
            flagged = False
        else:
            hours = 0.0
            flagged = True
        total += hours
        breakdown.append(
            {
                "name": component.name,
                "reference_count": len(refs),
                "estimated_hours": hours,
                "unbudgeted": flagged,
            }
        )
    total = round(total, 1)
    logger.info(
        "agent_tool_calculate_estimate",
        extra={"components": len(breakdown), "total_hours": total},
    )
    return {
        "components": breakdown,
        "total_hours": total,
        "contingency_factor": CONTINGENCY_FACTOR,
        "summary": f"total={total}h across {len(breakdown)} components",
    }


def validate_estimate(raw_args: dict[str, Any]) -> dict[str, Any]:
    """S4-style guardrails over the final estimate. No LLM."""
    args = ValidateEstimateArgs.model_validate(raw_args)
    issues: list[str] = []

    component_sum = 0.0
    for component in args.components:
        component_sum += component.estimated_hours
        if not component.reference_amounts:
            issues.append(f"{component.name!r} has no historical reference (unbudgeted).")
            continue
        low = min(component.reference_amounts) * 0.5
        high = max(component.reference_amounts) * 2.0
        if not (low <= component.estimated_hours <= high):
            issues.append(
                f"{component.name!r} estimate {component.estimated_hours}h is outside the "
                f"plausible range [{round(low, 1)}, {round(high, 1)}]h implied by its references."
            )

    if args.total_hours <= 0:
        issues.append("Total hours is non-positive.")
    if abs(component_sum - args.total_hours) > 0.5:
        issues.append(
            f"Total {args.total_hours}h does not match the sum of components "
            f"({round(component_sum, 1)}h)."
        )
    if args.total_hours > 20_000:
        issues.append(f"Total {args.total_hours}h is implausibly large for one project.")

    ok = not issues
    logger.info(
        "agent_tool_validate_estimate",
        extra={"ok": ok, "issues": len(issues)},
    )
    return {
        "ok": ok,
        "issues": issues,
        "summary": "estimate passed all guardrails" if ok else f"{len(issues)} issue(s) found",
    }
