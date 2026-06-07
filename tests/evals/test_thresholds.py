"""Unit tests for eval threshold constants."""

from __future__ import annotations

from tests.evals import thresholds as t


def test_soft_thresholds_are_sane() -> None:
    assert 0 < t.SOFT_HOURS_VARIANCE_RATIO < 1
    assert 0 < t.SOFT_COMPONENT_MIN_RUNS_RATIO <= 1
    assert 0 < t.SOFT_CONFIDENCE_DELTA < 1
    assert t.SOFT_CONSISTENCY_RUNS >= 2


def test_judge_thresholds_are_in_unit_interval() -> None:
    judge_constants = (
        t.SESSION_CONTEXT_USE_THRESHOLD,
        t.SCOPE_COHERENCE_THRESHOLD,
        t.JUSTIFICATION_QUALITY_THRESHOLD,
        t.CONFIDENCE_CALIBRATION_THRESHOLD,
        t.CROSS_TURN_CONSISTENCY_THRESHOLD,
        t.COMPLETENESS_FOR_SCOPE_THRESHOLD,
    )
    for value in judge_constants:
        assert 0 <= value <= 1
