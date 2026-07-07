"""Tests for advanced retrieval router/transform stubs (feature-061 Step 3)."""

from __future__ import annotations

import pytest

from app.embedding_pipeline.query_transform import transform_query
from app.embedding_pipeline.retrieval_debug_schemas import BranchResultEntry
from app.embedding_pipeline.retrieval_router import route_collection
from app.embedding_pipeline.temporal_decay import apply_temporal_decay


def test_route_collection_returns_budgets_stub() -> None:
    assert route_collection("OAuth backend", config_enabled=False, settings_enabled=False) == "budgets"
    assert route_collection("OAuth backend", config_enabled=True, settings_enabled=True) == "budgets"


@pytest.mark.asyncio
async def test_transform_query_passthrough_stub() -> None:
    assert await transform_query(
        "  OAuth backend  ",
        config_enabled=False,
        settings_enabled=False,
    ) == "  OAuth backend  "
    assert await transform_query(
        "OAuth backend",
        config_enabled=True,
        settings_enabled=True,
    ) == "OAuth backend"


def test_temporal_decay_noop_returns_same_entries() -> None:
    entries = [
        BranchResultEntry(rank=1, chunk_id=101, document_id=1, score=0.9),
        BranchResultEntry(rank=2, chunk_id=102, document_id=2, score=0.5),
    ]
    assert apply_temporal_decay(
        entries,
        config_enabled=True,
        settings_enabled=True,
    ) == entries
