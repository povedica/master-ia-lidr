"""Unit tests for eval assertion helpers."""

from __future__ import annotations

from app.schemas.estimation_result import EstimationLineItem, EstimationResult, EstimationTotals
from tests.evals.assertions import _component_present


def _estimate(*, summary: str, line_items: list[str]) -> EstimationResult:
    items = [
        EstimationLineItem(name=name, hours=8.0, cost_eur=400.0)
        for name in line_items
    ]
    totals = EstimationTotals(hours=sum(item.hours for item in items), cost_eur=sum(item.cost_eur for item in items))
    return EstimationResult(
        title="Test estimate",
        summary=summary,
        phases=[],
        line_items=items,
        totals=totals,
        duration_weeks=2.0,
        confidence=0.8,
        assumptions=["Assumption text for eval assertion unit test."],
        risks=["Risk text for eval assertion unit test."],
    )


def test_component_present_matches_alias_in_summary() -> None:
    estimate = _estimate(
        summary="Scope includes SSO login and executive dashboard widgets.",
        line_items=["Backend APIs"],
    )

    assert _component_present("authentication", estimate)
    assert _component_present("dashboard", estimate)


def test_component_present_matches_spanish_alias_in_english_output() -> None:
    estimate = _estimate(
        summary="Includes user authentication and ERP SAP integration.",
        line_items=["Admin panel development"],
    )

    assert _component_present("autenticación", estimate)
    assert _component_present("integración", estimate)
    assert _component_present("panel", estimate)
