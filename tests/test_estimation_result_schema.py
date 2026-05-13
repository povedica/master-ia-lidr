"""Domain ``EstimationResult`` schema and validators."""

from app.schemas.estimation_result import (
    EstimationLineItem,
    EstimationPhase,
    EstimationResult,
    EstimationTotals,
)


def _valid_result() -> EstimationResult:
    li = EstimationLineItem(name="Task A", hours=10.0, cost_eur=500.0)
    totals = EstimationTotals(hours=10.0, cost_eur=500.0)
    return EstimationResult(
        title="Project title for schema test",
        summary="S" * 25,
        phases=[EstimationPhase(name="Phase 1", items=[li])],
        line_items=[],
        totals=totals,
        duration_weeks=2.0,
        confidence=0.5,
    )


def test_model_json_schema_has_title_and_totals() -> None:
    schema = EstimationResult.model_json_schema()
    assert "title" in schema.get("properties", {})
    assert "totals" in schema.get("properties", {})


def test_totals_mismatch_normalized_from_line_items() -> None:
    li = EstimationLineItem(name="Task A", hours=10.0, cost_eur=500.0)
    bad_totals = EstimationTotals(hours=1.0, cost_eur=999.0)
    result = EstimationResult(
        title="Project title for schema test",
        summary="S" * 25,
        phases=[EstimationPhase(name="Phase 1", items=[li])],
        line_items=[],
        totals=bad_totals,
        duration_weeks=2.0,
        confidence=0.5,
    )
    assert result.totals.hours == 10.0
    assert result.totals.cost_eur == 500.0


def test_round_trip_valid_payload() -> None:
    original = _valid_result()
    data = original.model_dump(mode="json")
    restored = EstimationResult.model_validate(data)
    assert restored.title == original.title
