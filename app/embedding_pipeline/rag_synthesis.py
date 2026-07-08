"""Two-stage synthesis for per-task hours when neighbours contradict (FR-22)."""

from __future__ import annotations

import logging

from app.schemas.hour_range import HourRange
from app.schemas.rag_task_hours import TaskNeighborView

logger = logging.getLogger(__name__)


def is_contradiction(dispersion: float | None, threshold: float) -> bool:
    """True when neighbour spread crosses the contradiction threshold."""

    return dispersion is not None and dispersion > threshold


def _deterministic_range(neighbors: list[TaskNeighborView]) -> HourRange:
    hours = sorted(neighbor.estimated_hours for neighbor in neighbors)
    low, high = hours[0], hours[-1]
    return HourRange(
        low=low,
        high=high,
        reason=(
            f"historical sources disagree ({low}h vs {high}h across "
            f"{len(neighbors)} analogs); estimate depends on scope not yet pinned down"
        ),
    )


async def synthesize_range(
    neighbors: list[TaskNeighborView],
    dispersion: float | None,
    *,
    threshold: float,
    use_llm: bool = False,
    model: str | None = None,
) -> HourRange | None:
    """Return an hour range when neighbours contradict; otherwise ``None``."""

    del use_llm, model  # LLM reason phrasing deferred; deterministic path only for now.
    if not neighbors or not is_contradiction(dispersion, threshold):
        return None
    return _deterministic_range(neighbors)
