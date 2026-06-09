"""Tests for semantic search repository (feature-038)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.dialects import postgresql

from app.embedding_pipeline.search_repository import SemanticSearchRepository

EMBEDDING_DIM = 1536


def _query_vector(seed: float = 0.5) -> list[float]:
    return [seed + i * 0.0001 for i in range(EMBEDDING_DIM)]


def test_search_statement_uses_cosine_distance_and_filters_null_embeddings() -> None:
    repository = SemanticSearchRepository()
    statement = repository.build_search_statement(query_vector=_query_vector(), k=3)
    compiled = str(statement.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": False}))
    assert "<=>" in compiled
    assert "IS NOT NULL" in compiled.upper()


def test_search_statement_orders_by_distance_and_limits_k() -> None:
    repository = SemanticSearchRepository()
    statement = repository.build_search_statement(query_vector=_query_vector(), k=7)
    compiled = str(statement.compile(dialect=postgresql.dialect()))
    assert "ORDER BY" in compiled.upper()
    assert "LIMIT" in compiled.upper()


@pytest.mark.asyncio
async def test_search_chunks_maps_rows_to_search_results() -> None:
    repository = SemanticSearchRepository()
    row = SimpleNamespace(
        id=156,
        document_id=12,
        chunk_type="budget_component",
        content="Backend OAuth implementation",
        metadata_={"scope": "backend"},
        distance=0.231,
    )
    session = AsyncMock()
    result = MagicMock()
    result.all.return_value = [row]
    session.execute = AsyncMock(return_value=result)

    results = await repository.search_chunks(session, query_vector=_query_vector(), k=5)

    assert len(results) == 1
    assert results[0].chunk_id == 156
    assert results[0].document_id == 12
    assert results[0].chunk_type == "budget_component"
    assert results[0].content == "Backend OAuth implementation"
    assert results[0].distance == pytest.approx(0.231)
    assert results[0].metadata == {"scope": "backend"}


@pytest.mark.asyncio
async def test_search_chunks_returns_empty_list_when_no_rows() -> None:
    repository = SemanticSearchRepository()
    session = AsyncMock()
    result = MagicMock()
    result.all.return_value = []
    session.execute = AsyncMock(return_value=result)

    results = await repository.search_chunks(session, query_vector=_query_vector(), k=5)

    assert results == []
