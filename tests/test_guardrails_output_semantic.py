"""Tests for output semantic guardrails."""

from __future__ import annotations

from app.config import Settings
from app.guardrails.output_semantic import evaluate_output_semantic_guardrails
from app.schemas.estimation_request import EstimationRequest
from app.schemas.estimation_result import EstimationLineItem, EstimationResult, EstimationTotals
from tests.estimation_fixtures import minimal_estimation_request_dict


def _minimal_request() -> EstimationRequest:
    return EstimationRequest.model_validate(minimal_estimation_request_dict(evaluate=False))


def test_low_confidence_flagged() -> None:
    settings = Settings(openai_api_key="x", estimation_min_output_confidence=0.5)
    li = EstimationLineItem(name="Task", hours=1.0, cost_eur=1.0)
    totals = EstimationTotals(hours=1.0, cost_eur=1.0)
    result = EstimationResult(
        title="Low confidence project",
        summary="Summary text long enough for schema validation rules.",
        phases=[],
        line_items=[li],
        totals=totals,
        duration_weeks=1.0,
        confidence=0.1,
    )
    checks = evaluate_output_semantic_guardrails(
        request=_minimal_request(),
        result=result,
        settings=settings,
    )
    conf = next(c for c in checks if c.guardrail_id == "output_confidence_floor")
    assert conf.passed is False
