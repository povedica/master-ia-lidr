"""Tests for shared API response assembly."""

from datetime import UTC, datetime

from app.services.estimate_response_builder import assemble_estimate_response, dev_response_property_rows
from app.services.estimation_engine import EstimationMode
from app.services.llm_service import LlmEstimationCallOutcome, UsageInfo


def test_assemble_dev_mode_matches_expected_top_level_keys() -> None:
    result = LlmEstimationCallOutcome(
        estimation="## Estimation: test\n\n### Assumptions\nx\n",
        provider="openai",
        model="gpt-4o-mini",
        usage=UsageInfo(prompt_tokens=10, completion_tokens=5, total_tokens=15),
        mode=EstimationMode.STANDARD,
        assessment=None,
        mode_eligibility=None,
        finish_reason="stop",
    )
    finished = datetime(2026, 1, 15, 12, 0, 0, tzinfo=UTC)
    response, structure_check = assemble_estimate_response(
        result,
        evaluate=False,
        dev_mode=True,
        stats_log_enabled=False,
        request_id="est_abc123",
        finished_at=finished,
        latency_ms=42,
    )
    assert structure_check is None
    dumped = response.model_dump(mode="json", exclude_none=True)
    assert set(dumped.keys()) >= {
        "estimation",
        "mode",
        "model",
        "provider",
        "request_id",
        "latency_ms",
        "prompt_version",
        "examples_version",
        "usage",
        "finish_reason",
    }
    assert dumped["request_id"] == "est_abc123"
    assert dumped["latency_ms"] == 42


def test_dev_rows_sorted_by_field_name() -> None:
    result = LlmEstimationCallOutcome(
        estimation="# short",
        provider="openai",
        model="gpt-4o-mini",
        usage=None,
        mode=EstimationMode.BASIC,
        finish_reason="stop",
    )
    finished = datetime(2026, 1, 15, tzinfo=UTC)
    response, _ = assemble_estimate_response(
        result,
        evaluate=False,
        dev_mode=True,
        stats_log_enabled=False,
        request_id="est_xyz",
        finished_at=finished,
        latency_ms=1,
    )
    rows = dev_response_property_rows(response)
    names = [r["field"] for r in rows]
    assert names == sorted(names)


def test_evaluate_false_omits_score_in_serialised_rows() -> None:
    result = LlmEstimationCallOutcome(
        estimation="## Estimation: test\n\n### Assumptions\nx\n",
        provider="openai",
        model="gpt-4o-mini",
        usage=None,
        mode=EstimationMode.BASIC,
        finish_reason="stop",
    )
    finished = datetime(2026, 1, 15, tzinfo=UTC)
    response, _ = assemble_estimate_response(
        result,
        evaluate=False,
        dev_mode=True,
        stats_log_enabled=False,
        request_id="est_noscore",
        finished_at=finished,
        latency_ms=0,
    )
    rows = dev_response_property_rows(response)
    assert not any(r["field"] == "score" for r in rows)


def test_evaluate_true_includes_score_and_nested_blocks() -> None:
    body = (
        "## Estimation: mocked output\n\n"
        "### Assumptions\nx\n### Estimate\ny\n### Risks\nz\n"
        "| Task | Hours | Cost (EUR) |\n| --- | --- | --- |\n| a | 1 | 1 |\n"
    )
    result = LlmEstimationCallOutcome(
        estimation=body,
        provider="openai",
        model="gpt-4o-mini",
        usage=None,
        mode=EstimationMode.BASIC,
        finish_reason="stop",
    )
    finished = datetime(2026, 1, 15, tzinfo=UTC)
    response, _ = assemble_estimate_response(
        result,
        evaluate=True,
        dev_mode=True,
        stats_log_enabled=False,
        request_id="est_scored",
        finished_at=finished,
        latency_ms=0,
    )
    rows = dev_response_property_rows(response)
    fields = {r["field"] for r in rows}
    assert "score" in fields
    assert "output_validation" in fields
    assert "structure_evaluation" in fields
