"""Unit tests for task-hours synthesis (feature-053 FR-22)."""

from __future__ import annotations

import asyncio
import statistics

from app.embedding_pipeline.rag_synthesis import is_contradiction, synthesize_range
from app.schemas.hour_range import HourRange
from app.schemas.rag_task_hours import TaskNeighborView


def _neighbors(hours: list[int]) -> list[TaskNeighborView]:
    return [
        TaskNeighborView(
            chunk_id=i,
            budget_id=f"TASK-{i}",
            estimated_hours=h,
            distance=0.2 + i * 0.02,
        )
        for i, h in enumerate(hours)
    ]


def _dispersion(hours: list[int]) -> float:
    mean = statistics.fmean(hours)
    return statistics.pstdev(hours) / mean


def test_is_contradiction_threshold() -> None:
    assert is_contradiction(0.4, 0.35) is True
    assert is_contradiction(0.2, 0.35) is False
    assert is_contradiction(None, 0.35) is False


def test_synthesize_range_emits_range_on_contradiction() -> None:
    hours = [40, 90]
    rng = asyncio.run(
        synthesize_range(_neighbors(hours), _dispersion(hours), threshold=0.35, use_llm=False)
    )
    assert isinstance(rng, HourRange)
    assert rng.low == 40
    assert rng.high == 90
    assert "40h" in rng.reason and "90h" in rng.reason


def test_synthesize_range_none_when_sources_agree() -> None:
    hours = [50, 52, 48]
    rng = asyncio.run(
        synthesize_range(_neighbors(hours), _dispersion(hours), threshold=0.35, use_llm=False)
    )
    assert rng is None


def test_synthesize_range_none_without_neighbors() -> None:
    rng = asyncio.run(synthesize_range([], 0.9, threshold=0.35, use_llm=False))
    assert rng is None
