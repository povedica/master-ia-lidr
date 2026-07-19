"""Review-policy signals for conditional HITL (feature-067)."""

from __future__ import annotations

import pytest

from app.services.estimation_graph.review_policy import (
    ReviewSignals,
    requires_human_review,
    review_reasons,
)


def test_requires_review_when_confidence_below_threshold() -> None:
    signals = ReviewSignals(
        confidence=0.69,
        out_of_historical_range=False,
        no_precedent=False,
    )
    assert requires_human_review(signals, threshold=0.70) is True
    assert "confidence below threshold" in review_reasons(signals, threshold=0.70)


def test_confidence_at_threshold_does_not_trigger_alone() -> None:
    signals = ReviewSignals(
        confidence=0.70,
        out_of_historical_range=False,
        no_precedent=False,
    )
    assert requires_human_review(signals, threshold=0.70) is False
    assert review_reasons(signals, threshold=0.70) == []


def test_out_of_range_triggers_review() -> None:
    signals = ReviewSignals(
        confidence=0.95,
        out_of_historical_range=True,
        no_precedent=False,
    )
    assert requires_human_review(signals, threshold=0.70) is True
    assert "estimate outside historical range" in review_reasons(signals, threshold=0.70)


def test_no_precedent_triggers_review() -> None:
    signals = ReviewSignals(
        confidence=0.95,
        out_of_historical_range=False,
        no_precedent=True,
    )
    assert requires_human_review(signals, threshold=0.70) is True
    assert "no relevant historical precedent" in review_reasons(signals, threshold=0.70)


def test_multiple_review_reasons_are_collected() -> None:
    signals = ReviewSignals(
        confidence=0.1,
        out_of_historical_range=True,
        no_precedent=True,
    )
    reasons = review_reasons(signals, threshold=0.70)
    assert requires_human_review(signals, threshold=0.70) is True
    assert reasons == [
        "confidence below threshold",
        "estimate outside historical range",
        "no relevant historical precedent",
    ]


@pytest.mark.parametrize(
    ("confidence", "threshold", "expected"),
    [
        (0.0, 0.70, True),
        (0.699999, 0.70, True),
        (0.70, 0.70, False),
        (1.0, 0.70, False),
    ],
)
def test_confidence_threshold_boundaries(
    confidence: float, threshold: float, expected: bool
) -> None:
    signals = ReviewSignals(
        confidence=confidence,
        out_of_historical_range=False,
        no_precedent=False,
    )
    assert requires_human_review(signals, threshold=threshold) is expected
