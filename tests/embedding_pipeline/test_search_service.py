"""Tests for semantic search service orchestration (feature-038)."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.embedding_pipeline.schemas import SearchRequest, SearchResult
from app.embedding_pipeline.search import run_semantic_search

EMBEDDING_DIM = 1536


def _query_vector(seed: float = 0.5) -> list[float]:
    return [seed + i * 0.0001 for i in range(EMBEDDING_DIM)]


class _FakeEmbedder:
    def __init__(self, vector: list[float] | None = None) -> None:
        self.vector = vector or _query_vector()
        self.embed_one_calls = 0

    async def embed_one(self, text: str) -> list[float]:
        self.embed_one_calls += 1
        return self.vector


class _FakeRepository:
    def __init__(self, results: list[SearchResult] | None = None) -> None:
        self.results = results or []
        self.last_query_vector: list[float] | None = None
        self.last_k: int | None = None

    async def search_chunks(
        self,
        session: AsyncSession,
        *,
        query_vector: list[float],
        k: int,
    ) -> list[SearchResult]:
        del session
        self.last_query_vector = query_vector
        self.last_k = k
        return self.results[:k]


@pytest.mark.asyncio
async def test_run_semantic_search_calls_embed_one_once() -> None:
    embedder = _FakeEmbedder()
    repository = _FakeRepository()
    request = SearchRequest(query="OAuth fintech backend", k=3)
    session = AsyncMock(spec=AsyncSession)

    response = await run_semantic_search(
        request,
        session=session,
        embedder=embedder,  # type: ignore[arg-type]
        repository=repository,  # type: ignore[arg-type]
    )

    assert embedder.embed_one_calls == 1
    assert repository.last_k == 3
    assert repository.last_query_vector == embedder.vector
    assert response.query == "OAuth fintech backend"
    assert response.k == 3
    assert response.results == []
    assert response.search_time_ms >= 0


@pytest.mark.asyncio
async def test_run_semantic_search_returns_repository_results() -> None:
    results = [
        SearchResult(
            chunk_id=1,
            document_id=10,
            chunk_type="budget_component",
            content="First",
            distance=0.1,
            metadata={},
        ),
        SearchResult(
            chunk_id=2,
            document_id=10,
            chunk_type="budget_component",
            content="Second",
            distance=0.2,
            metadata={},
        ),
    ]
    embedder = _FakeEmbedder()
    repository = _FakeRepository(results=results)
    request = SearchRequest(query="REST API", k=5)
    session = AsyncMock(spec=AsyncSession)

    response = await run_semantic_search(
        request,
        session=session,
        embedder=embedder,  # type: ignore[arg-type]
        repository=repository,  # type: ignore[arg-type]
    )

    assert len(response.results) == 2
    assert response.results[0].distance == pytest.approx(0.1)
    assert response.results[1].chunk_id == 2
