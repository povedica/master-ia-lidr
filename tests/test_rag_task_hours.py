"""Unit tests for per-task hours consensus (feature-062)."""

from __future__ import annotations

import pytest

from app.services.rag_task_hours import compose_task_search_text, consensus_hours


def test_compose_task_search_text_includes_module_and_task() -> None:
    text = compose_task_search_text(
        module="Authentication",
        name="OAuth integration",
        description="Add Google login",
    )
    assert "Module: Authentication" in text
    assert "Task: OAuth integration" in text
    assert "Google login" in text


def test_consensus_hours_weighted_mean() -> None:
    hours, reliability, dispersion = consensus_hours([(8, 0.1), (12, 0.2)])
    assert hours in {9, 10, 11}
    assert 0.0 <= reliability <= 1.0
    assert dispersion >= 0.0


def test_consensus_hours_single_neighbor() -> None:
    hours, reliability, dispersion = consensus_hours([(40, 0.05)])
    assert hours == 40
    assert dispersion == 0.0
    assert reliability > 0.9


def test_consensus_hours_requires_neighbors() -> None:
    with pytest.raises(ValueError, match="non-empty"):
        consensus_hours([])
