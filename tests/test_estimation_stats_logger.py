"""Unit tests for estimation stats NDJSON logging."""

import json
from datetime import UTC, datetime
from pathlib import Path

from app.services.estimation_engine import (
    EstimationMode,
    InputAssessment,
    ModeEligibility,
)
from app.services.estimation_stats_logger import (
    append_estimation_stats_line,
    build_estimation_stats_record,
    resolve_stats_log_path,
)
from app.services.llm_service import EstimationResult, UsageInfo


def test_build_estimation_stats_record_omits_estimation_and_matches_shape() -> None:
    assessment = InputAssessment(
        detail_level="medium",
        recommended_mode=EstimationMode.STANDARD,
        reason="Test reason.",
    )
    eligibility = ModeEligibility(
        allowed_modes=(EstimationMode.BASIC, EstimationMode.STANDARD),
        blocked_modes=(EstimationMode.PROFESSIONAL, EstimationMode.EXPERT_REVIEW),
        reason="Input detail is insufficient.",
    )
    result = EstimationResult(
        estimation="## Estimation: secret body",
        provider="openai",
        model="gpt-4o-mini",
        usage=UsageInfo(prompt_tokens=10, completion_tokens=20, total_tokens=30),
        mode=EstimationMode.BASIC,
        assessment=assessment,
        mode_eligibility=eligibility,
        finish_reason="stop",
    )
    ts = datetime(2026, 4, 30, 15, 11, 41, 959966, tzinfo=UTC)
    record = build_estimation_stats_record(
        result=result,
        structure_score=0.4186,
        request_id="est_abc",
        timestamp=ts,
        latency_ms=5703,
        prompt_version="v7-guided-input",
        examples_version="file-mode-v4-estimator-layout",
        estimated_cost_usd=0.00041295,
    )

    assert "estimation" not in record
    assert record["request_id"] == "est_abc"
    assert record["mode"] == "basic"
    assert record["latency_ms"] == 5703
    assert record["timestamp"].endswith("Z")
    assert record["assessment"]["recommended_mode"] == "standard"
    assert record["mode_eligibility"]["blocked_modes"] == ["professional", "expert_review"]
    assert record["usage"]["total_tokens"] == 30
    assert record["usage"]["preprocessing_input_tokens"] == 0
    assert record["usage"]["preprocessing_output_tokens"] == 0
    assert record["usage"]["estimated_cost_usd"] == 0.00041295
    assert record["degraded"] is False
    assert record["score"] == 0.4186
    assert record["finish_reason"] == "stop"


def test_resolve_stats_log_path_default_when_empty() -> None:
    path = resolve_stats_log_path("")
    assert path.name == "estimation-stats.jsonl"
    assert path.parent.name == "output-stats"


def test_append_estimation_stats_line_writes_ndjson(tmp_path: Path) -> None:
    path = tmp_path / "stats.jsonl"
    append_estimation_stats_line(
        path,
        {"request_id": "est_1", "latency_ms": 1},
    )
    append_estimation_stats_line(
        path,
        {"request_id": "est_2", "latency_ms": 2},
    )
    lines = path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0])["request_id"] == "est_1"
    assert json.loads(lines[1])["latency_ms"] == 2
