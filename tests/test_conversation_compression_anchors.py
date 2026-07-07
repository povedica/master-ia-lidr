"""Anchor detector tests (feature-064)."""

from __future__ import annotations

import pytest

from app.services.conversation_compression import AnchorDetector


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("We agreed to lock the budget at 120k", True),
        ("The scope is frozen for this release", True),
        ("What is the weather today?", False),
    ],
)
def test_anchor_detector_heuristic(text: str, expected: bool) -> None:
    detector = AnchorDetector(mode="heuristic")
    match = detector.detect(text)
    assert match.is_anchor is expected
