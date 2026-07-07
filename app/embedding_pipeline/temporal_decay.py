"""Temporal decay weighting for advanced retrieval (feature-061 no-op stub)."""

from __future__ import annotations

from app.embedding_pipeline.retrieval_debug_schemas import BranchResultEntry


def apply_temporal_decay(
    entries: list[BranchResultEntry],
    *,
    config_enabled: bool,
    settings_enabled: bool,
) -> list[BranchResultEntry]:
    """Apply recency weighting when metadata supports it.

    No-op stub in this slice: returns ``entries`` unchanged when decay metadata
    is unavailable.
    """

    del config_enabled, settings_enabled
    return entries
