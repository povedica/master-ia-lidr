"""Safe structured placeholders when guardrails return a filtered response."""

from __future__ import annotations

from app.schemas.estimation_result import EstimationResult, EstimationTotals


def build_degraded_estimation_result(*, user_summary: str) -> EstimationResult:
    """Build a minimal valid ``EstimationResult`` for degraded / filtered responses."""

    summary = user_summary.strip()
    if len(summary) < 20:
        summary = (summary + " " + ("." * 20))[:2000]
    summary = summary[:2000]
    totals = EstimationTotals(hours=0.0, cost_eur=0.0)
    return EstimationResult(
        title="Estimation unavailable",
        summary=summary,
        phases=[],
        line_items=[],
        totals=totals,
        duration_weeks=1.0,
        confidence=0.0,
        assumptions=["Response limited by automated safety checks."],
        risks=["Detailed estimate was not generated."],
        recommended_team=[],
    )
