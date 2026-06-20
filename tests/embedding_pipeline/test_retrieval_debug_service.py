"""Tests for retrieval debug service orchestration (feature-042)."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.embedding_pipeline.retrieval_debug import run_retrieval_debug
from app.embedding_pipeline.retrieval_debug_schemas import RetrievalDebugRequest
from app.embedding_pipeline.schemas import SearchResult

EMBEDDING_DIM = 1536


def _query_vector(seed: float = 0.5) -> list[float]:
    return [seed + i * 0.0001 for i in range(EMBEDDING_DIM)]


class _FakeEmbedder:
    def __init__(self, vector: list[float] | None = None) -> None:
        self.vector = vector or _query_vector()
        self.embed_one_calls = 0
        self.last_query: str | None = None

    async def embed_one(self, text: str) -> list[float]:
        self.embed_one_calls += 1
        self.last_query = text
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


def _search_result(
    *,
    chunk_id: int,
    document_id: int = 12,
    distance: float,
    content: str = "Backend OAuth implementation with refresh token rotation",
    metadata: dict[str, object] | None = None,
) -> SearchResult:
    return SearchResult(
        chunk_id=chunk_id,
        document_id=document_id,
        chunk_type="budget_component",
        content=content,
        distance=distance,
        metadata=metadata or {"budget_id": "BUD-2024-014", "component_id": "AUTH-001"},
    )


@pytest.mark.asyncio
async def test_run_retrieval_debug_calls_embedder_once_and_returns_vector_trace() -> None:
    embedder = _FakeEmbedder()
    repository = _FakeRepository(
        results=[
            _search_result(chunk_id=101, distance=0.2),
            _search_result(chunk_id=102, distance=0.6),
        ]
    )
    request = RetrievalDebugRequest(
        query="OAuth refresh token rotation",
        vector={"top_k": 5},
        max_results=1,
    )
    session = AsyncMock(spec=AsyncSession)

    response = await run_retrieval_debug(
        request,
        session=session,
        embedder=embedder,  # type: ignore[arg-type]
        repository=repository,  # type: ignore[arg-type]
    )

    assert embedder.embed_one_calls == 1
    assert embedder.last_query == "OAuth refresh token rotation"
    assert repository.last_k == 5
    assert repository.last_query_vector == embedder.vector
    assert response.branches.vector is not None
    assert [entry.rank for entry in response.branches.vector] == [1, 2]
    assert response.branches.lexical is None
    assert len(response.final_results) == 1
    result = response.final_results[0]
    assert result.final_position == 1
    assert result.chunk_id == 101
    assert result.semantic_rank == 1
    assert result.semantic_score == pytest.approx(0.8)
    assert result.semantic_distance == pytest.approx(0.2)
    assert result.source_strategies == ["vector"]
    assert result.title == "BUD-2024-014 AUTH-001"
    assert "Backend OAuth implementation" in result.content_excerpt
    assert result.explanation.signals == ["semantic_strong"]
    assert response.timings_ms["vector"] >= 0
    assert response.timings_ms["total"] >= response.timings_ms["vector"]


@pytest.mark.asyncio
async def test_run_retrieval_debug_warns_for_unimplemented_branches() -> None:
    embedder = _FakeEmbedder()
    repository = _FakeRepository()
    request = RetrievalDebugRequest(query="OAuth", strategies=["vector", "lexical"])
    session = AsyncMock(spec=AsyncSession)

    response = await run_retrieval_debug(
        request,
        session=session,
        embedder=embedder,  # type: ignore[arg-type]
        repository=repository,  # type: ignore[arg-type]
    )

    assert response.branches.vector == []
    assert response.branches.lexical is None
    assert "Strategy 'lexical' is not implemented yet." in response.warnings


@pytest.mark.asyncio
async def test_run_retrieval_debug_applies_threshold_before_final_results() -> None:
    embedder = _FakeEmbedder()
    repository = _FakeRepository(
        results=[
            _search_result(chunk_id=101, distance=0.25),
            _search_result(chunk_id=102, distance=0.55),
        ]
    )
    request = RetrievalDebugRequest(
        query="OAuth",
        vector={"top_k": 5, "threshold": 0.6},
        max_results=10,
    )
    session = AsyncMock(spec=AsyncSession)

    response = await run_retrieval_debug(
        request,
        session=session,
        embedder=embedder,  # type: ignore[arg-type]
        repository=repository,  # type: ignore[arg-type]
    )

    assert response.branches.vector is not None
    assert [entry.chunk_id for entry in response.branches.vector] == [101, 102]
    assert [result.chunk_id for result in response.final_results] == [101]
