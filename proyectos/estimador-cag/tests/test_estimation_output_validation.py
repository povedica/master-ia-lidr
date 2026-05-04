"""Tests for deterministic output validation (separate from input routing score)."""

from app.services.estimation_engine import EstimationMode
from app.services.estimation_output_validation import evaluate_estimation_output


def test_evaluate_marks_truncated_finish_reason() -> None:
    view = evaluate_estimation_output(
        "## Estimation\n### Assumptions\na\n### Estimate\nb\n### Risks\nc\n",
        EstimationMode.BASIC,
        "length",
    )
    assert view.finish_reason_ok is False
    assert any("finish_reason" in i for i in view.issues)


def test_evaluate_all_ok_for_basic_stop() -> None:
    text = (
        "## Estimation\n### Assumptions\na\n### Estimate\nb\n### Risks\nc\n"
    )
    view = evaluate_estimation_output(text, EstimationMode.BASIC, "stop")
    assert view.finish_reason_ok is True
    assert view.structure_valid is True
    assert view.issues == []
