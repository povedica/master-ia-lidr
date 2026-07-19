"""Deterministic policy for conditional human review (feature-067)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ReviewSignals:
    """Normalized signals derived from validation + evidence."""

    confidence: float
    out_of_historical_range: bool
    no_precedent: bool


def review_reasons(signals: ReviewSignals, *, threshold: float) -> list[str]:
    """Return stable, ordered human-review reasons for the given signals."""
    reasons: list[str] = []
    if signals.confidence < threshold:
        reasons.append("confidence below threshold")
    if signals.out_of_historical_range:
        reasons.append("estimate outside historical range")
    if signals.no_precedent:
        reasons.append("no relevant historical precedent")
    return reasons


def requires_human_review(signals: ReviewSignals, *, threshold: float) -> bool:
    """True when any configured review-policy condition is met."""
    return bool(review_reasons(signals, threshold=threshold))
