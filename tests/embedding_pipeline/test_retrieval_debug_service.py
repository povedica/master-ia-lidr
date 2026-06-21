"""Tests for retrieval debug service orchestration (feature-042)."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.embedding_pipeline.lexical_search_repository import LexicalSearchResult
from app.embedding_pipeline.rerank import RerankCandidate, RerankedItem
from app.embedding_pipeline.retrieval_debug import run_retrieval_debug
from app.embedding_pipeline.retrieval_debug_schemas import (
    RetrievalDebugRequest,
    RetrievalMetadataFilters,
)
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
        self.last_filters: RetrievalMetadataFilters | None = None

    async def search_chunks(
        self,
        session: AsyncSession,
        *,
        query_vector: list[float],
        k: int,
        filters: RetrievalMetadataFilters | None = None,
    ) -> list[SearchResult]:
        del session
        self.last_query_vector = query_vector
        self.last_k = k
        self.last_filters = filters
        return self.results[:k]


class _FakeLexicalRepository:
    def __init__(
        self,
        results: list[LexicalSearchResult] | None = None,
        error: Exception | None = None,
    ) -> None:
        self.results = results or []
        self.error = error
        self.last_query: str | None = None
        self.last_top_k: int | None = None
        self.last_filters: RetrievalMetadataFilters | None = None

    async def search_chunks(
        self,
        session: AsyncSession,
        *,
        query: str,
        top_k: int,
        filters: RetrievalMetadataFilters | None = None,
    ) -> list[LexicalSearchResult]:
        del session
        self.last_query = query
        self.last_top_k = top_k
        self.last_filters = filters
        if self.error is not None:
            raise self.error
        return self.results[:top_k]


class _FakeReorderReranker:
    is_noop = False

    async def rerank(
        self,
        query: str,
        candidates: list[RerankCandidate],
    ) -> list[RerankedItem]:
        del query
        reordered = [candidates[1], candidates[0], *candidates[2:]]
        return [
            RerankedItem(
                candidate=candidate,
                rerank_rank=rank,
                rerank_score=1.0 - (rank * 0.1),
            )
            for rank, candidate in enumerate(reordered, start=1)
        ]


class _FakeFilterReranker:
    is_noop = False

    async def rerank(
        self,
        query: str,
        candidates: list[RerankCandidate],
    ) -> list[RerankedItem]:
        del query
        kept = [candidates[0], *candidates[2:]]
        return [
            RerankedItem(
                candidate=candidate,
                rerank_rank=rank,
                rerank_score=0.9 - (rank * 0.1),
            )
            for rank, candidate in enumerate(kept, start=1)
        ]


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


def _lexical_result(
    *,
    chunk_id: int,
    document_id: int = 12,
    ts_rank: float,
    content: str = "JWT OAuth2 implementation with refresh token rotation",
    metadata: dict[str, object] | None = None,
    matched_terms: list[str] | None = None,
) -> LexicalSearchResult:
    return LexicalSearchResult(
        chunk_id=chunk_id,
        document_id=document_id,
        chunk_type="budget_component",
        content=content,
        metadata=metadata or {"budget_id": "BUD-2024-014", "component_id": "AUTH-001"},
        ts_rank=ts_rank,
        matched_terms=matched_terms or ["jwt", "oauth2"],
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
async def test_run_retrieval_debug_omits_rerank_when_disabled() -> None:
    embedder = _FakeEmbedder()
    repository = _FakeRepository()
    request = RetrievalDebugRequest(query="OAuth", strategies=["vector", "rerank"])
    session = AsyncMock(spec=AsyncSession)

    response = await run_retrieval_debug(
        request,
        session=session,
        embedder=embedder,  # type: ignore[arg-type]
        repository=repository,  # type: ignore[arg-type]
    )

    assert response.branches.vector == []
    assert response.branches.lexical is None
    assert response.branches.rerank is None
    assert response.warnings == []


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


@pytest.mark.asyncio
async def test_run_retrieval_debug_returns_lexical_only_trace_without_embedding() -> None:
    embedder = _FakeEmbedder()
    lexical_repository = _FakeLexicalRepository(
        results=[
            _lexical_result(chunk_id=201, ts_rank=0.8, matched_terms=["jwt", "oauth2"]),
            _lexical_result(chunk_id=202, ts_rank=0.2, matched_terms=["jwt"]),
        ]
    )
    request = RetrievalDebugRequest(
        query="JWT OAuth2",
        strategies=["lexical"],
        lexical={"top_k": 5},
        max_results=1,
    )
    session = AsyncMock(spec=AsyncSession)

    response = await run_retrieval_debug(
        request,
        session=session,
        embedder=embedder,  # type: ignore[arg-type]
        repository=_FakeRepository(),  # type: ignore[arg-type]
        lexical_repository=lexical_repository,  # type: ignore[arg-type]
    )

    assert embedder.embed_one_calls == 0
    assert lexical_repository.last_query == "JWT OAuth2"
    assert lexical_repository.last_top_k == 5
    assert response.branches.vector is None
    assert response.branches.lexical is not None
    assert [entry.chunk_id for entry in response.branches.lexical] == [201, 202]
    assert response.branches.lexical[0].matched_terms == ["jwt", "oauth2"]
    assert len(response.final_results) == 1
    result = response.final_results[0]
    assert result.chunk_id == 201
    assert result.semantic_score is None
    assert result.lexical_rank == 1
    assert result.lexical_score == pytest.approx(1.0)
    assert result.matched_terms == ["jwt", "oauth2"]
    assert result.source_strategies == ["lexical"]
    assert result.explanation.signals == ["lexical_exact_match"]


@pytest.mark.asyncio
async def test_run_retrieval_debug_enriches_vector_results_with_lexical_fields() -> None:
    embedder = _FakeEmbedder()
    repository = _FakeRepository(
        results=[
            _search_result(chunk_id=101, distance=0.2),
            _search_result(chunk_id=102, distance=0.6),
        ]
    )
    lexical_repository = _FakeLexicalRepository(
        results=[
            _lexical_result(chunk_id=101, ts_rank=0.7, matched_terms=["oauth2"]),
        ]
    )
    request = RetrievalDebugRequest(query="OAuth2", strategies=["vector", "lexical"])
    session = AsyncMock(spec=AsyncSession)

    response = await run_retrieval_debug(
        request,
        session=session,
        embedder=embedder,  # type: ignore[arg-type]
        repository=repository,  # type: ignore[arg-type]
        lexical_repository=lexical_repository,  # type: ignore[arg-type]
    )

    assert response.branches.vector is not None
    assert response.branches.lexical is not None
    result = response.final_results[0]
    assert result.chunk_id == 101
    assert result.semantic_rank == 1
    assert result.lexical_rank == 1
    assert result.lexical_score == pytest.approx(1.0)
    assert result.matched_terms == ["oauth2"]
    assert result.source_strategies == ["vector", "lexical"]


@pytest.mark.asyncio
async def test_run_retrieval_debug_returns_hybrid_branch_diff_and_explanations() -> None:
    embedder = _FakeEmbedder()
    repository = _FakeRepository(
        results=[
            _search_result(chunk_id=101, distance=0.2),
            _search_result(chunk_id=102, distance=0.3),
        ]
    )
    lexical_repository = _FakeLexicalRepository(
        results=[
            _lexical_result(
                chunk_id=103,
                document_id=13,
                ts_rank=0.9,
                content="JWT refresh token rotation",
                matched_terms=["jwt"],
            ),
            _lexical_result(chunk_id=101, ts_rank=0.1, matched_terms=["oauth2"]),
        ]
    )
    request = RetrievalDebugRequest(
        query="JWT OAuth2",
        strategies=["vector", "lexical", "hybrid"],
        hybrid={"method": "weighted", "weights": {"vector": 1.0, "lexical": 3.0}},
        max_results=2,
    )
    session = AsyncMock(spec=AsyncSession)

    response = await run_retrieval_debug(
        request,
        session=session,
        embedder=embedder,  # type: ignore[arg-type]
        repository=repository,  # type: ignore[arg-type]
        lexical_repository=lexical_repository,  # type: ignore[arg-type]
    )

    assert response.branches.hybrid is not None
    assert [entry.chunk_id for entry in response.branches.hybrid] == [103, 101, 102]
    assert [result.chunk_id for result in response.final_results] == [103, 101]
    assert response.final_results[0].fusion_rank == 1
    assert response.final_results[0].fusion_score == pytest.approx(0.75)
    assert response.final_results[0].source_strategies == ["lexical", "hybrid"]
    assert response.final_results[0].explanation.signals == [
        "lexical_exact_match",
        "hybrid_rescued",
    ]
    assert response.final_results[1].source_strategies == ["vector", "lexical", "hybrid"]
    assert response.diff is not None
    assert [entry.chunk_id for entry in response.diff.common] == [101]
    assert [entry.chunk_id for entry in response.diff.lexical_only] == [103]
    assert [entry.chunk_id for entry in response.diff.hybrid_rescued] == [103]
    assert response.diff.dropped_by_rerank == []
    assert response.timings_ms["hybrid"] >= 0
    assert response.warnings == []


@pytest.mark.asyncio
async def test_run_retrieval_debug_passes_filters_to_candidate_branches_and_echoes_config() -> None:
    embedder = _FakeEmbedder()
    repository = _FakeRepository(results=[_search_result(chunk_id=101, distance=0.2)])
    lexical_repository = _FakeLexicalRepository(results=[_lexical_result(chunk_id=101, ts_rank=0.8)])
    request = RetrievalDebugRequest(
        query="JWT OAuth2",
        strategies=["vector", "lexical", "hybrid"],
        filters={
            "client_sector": "finance",
            "tags": ["backend", "api"],
            "year": {"from": 2023, "to": 2025},
        },
    )
    session = AsyncMock(spec=AsyncSession)

    response = await run_retrieval_debug(
        request,
        session=session,
        embedder=embedder,  # type: ignore[arg-type]
        repository=repository,  # type: ignore[arg-type]
        lexical_repository=lexical_repository,  # type: ignore[arg-type]
    )

    assert repository.last_filters == request.filters
    assert lexical_repository.last_filters == request.filters
    assert response.applied_config["filters"] == {
        "client_sector": "finance",
        "tags": ["backend", "api"],
        "year": {"from": 2023, "to": 2025},
    }


@pytest.mark.asyncio
async def test_run_retrieval_debug_with_filters_allows_empty_branch_results() -> None:
    embedder = _FakeEmbedder()
    repository = _FakeRepository()
    lexical_repository = _FakeLexicalRepository()
    request = RetrievalDebugRequest(
        query="JWT OAuth2",
        strategies=["vector", "lexical", "hybrid"],
        filters={"client_sector": "nonexistent"},
    )
    session = AsyncMock(spec=AsyncSession)

    response = await run_retrieval_debug(
        request,
        session=session,
        embedder=embedder,  # type: ignore[arg-type]
        repository=repository,  # type: ignore[arg-type]
        lexical_repository=lexical_repository,  # type: ignore[arg-type]
    )

    assert response.branches.vector == []
    assert response.branches.lexical == []
    assert response.branches.hybrid == []
    assert response.final_results == []
    assert response.warnings == []


@pytest.mark.asyncio
async def test_run_retrieval_debug_noop_rerank_preserves_hybrid_order_with_warning() -> None:
    embedder = _FakeEmbedder()
    repository = _FakeRepository(
        results=[
            _search_result(chunk_id=101, distance=0.2),
            _search_result(chunk_id=102, distance=0.3),
        ]
    )
    lexical_repository = _FakeLexicalRepository(
        results=[
            _lexical_result(
                chunk_id=103,
                document_id=13,
                ts_rank=0.9,
                content="JWT refresh token rotation",
                matched_terms=["jwt"],
            ),
            _lexical_result(chunk_id=101, ts_rank=0.1, matched_terms=["oauth2"]),
        ]
    )
    request = RetrievalDebugRequest(
        query="JWT OAuth2",
        strategies=["vector", "lexical", "hybrid", "rerank"],
        hybrid={"method": "weighted", "weights": {"vector": 1.0, "lexical": 3.0}},
        rerank={"enabled": True},
        max_results=2,
    )
    session = AsyncMock(spec=AsyncSession)

    response = await run_retrieval_debug(
        request,
        session=session,
        embedder=embedder,  # type: ignore[arg-type]
        repository=repository,  # type: ignore[arg-type]
        lexical_repository=lexical_repository,  # type: ignore[arg-type]
    )

    assert response.branches.rerank is not None
    assert [entry.chunk_id for entry in response.branches.rerank] == [103, 101]
    assert [result.chunk_id for result in response.final_results] == [103, 101]
    assert [result.rerank_rank for result in response.final_results] == [1, 2]
    assert [result.rerank_score for result in response.final_results] == [None, None]
    assert all("rerank" in result.source_strategies for result in response.final_results)
    assert response.diff is not None
    assert response.diff.dropped_by_rerank == []
    assert response.timings_ms["rerank"] >= 0
    assert (
        "rerank.enabled=true but no reranker configured; rerank is a no-op placeholder"
        in response.warnings
    )


@pytest.mark.asyncio
async def test_run_retrieval_debug_fake_reranker_reorders_and_marks_signals() -> None:
    embedder = _FakeEmbedder()
    repository = _FakeRepository(
        results=[
            _search_result(chunk_id=101, distance=0.2),
            _search_result(chunk_id=102, distance=0.3),
        ]
    )
    lexical_repository = _FakeLexicalRepository(
        results=[
            _lexical_result(chunk_id=103, document_id=13, ts_rank=0.9),
            _lexical_result(chunk_id=101, ts_rank=0.1),
        ]
    )
    request = RetrievalDebugRequest(
        query="JWT OAuth2",
        strategies=["vector", "lexical", "hybrid", "rerank"],
        hybrid={"method": "weighted", "weights": {"vector": 1.0, "lexical": 3.0}},
        rerank={"enabled": True},
        max_results=2,
    )
    session = AsyncMock(spec=AsyncSession)

    response = await run_retrieval_debug(
        request,
        session=session,
        embedder=embedder,  # type: ignore[arg-type]
        repository=repository,  # type: ignore[arg-type]
        lexical_repository=lexical_repository,  # type: ignore[arg-type]
        reranker=_FakeReorderReranker(),
    )

    assert response.branches.rerank is not None
    assert [entry.chunk_id for entry in response.branches.rerank] == [101, 103]
    assert [result.chunk_id for result in response.final_results] == [101, 103]
    assert response.final_results[0].rerank_rank == 1
    assert response.final_results[0].rerank_score == pytest.approx(0.9)
    assert "rerank_promoted" in response.final_results[0].explanation.signals
    assert "rerank_demoted" in response.final_results[1].explanation.signals


@pytest.mark.asyncio
async def test_run_retrieval_debug_fake_reranker_filters_dropped_results() -> None:
    embedder = _FakeEmbedder()
    repository = _FakeRepository(
        results=[
            _search_result(chunk_id=101, distance=0.2),
            _search_result(chunk_id=102, distance=0.3),
        ]
    )
    lexical_repository = _FakeLexicalRepository(
        results=[
            _lexical_result(chunk_id=103, document_id=13, ts_rank=0.9),
            _lexical_result(chunk_id=101, ts_rank=0.1),
            _lexical_result(chunk_id=104, document_id=14, ts_rank=0.05),
        ]
    )
    request = RetrievalDebugRequest(
        query="JWT OAuth2",
        strategies=["vector", "lexical", "hybrid", "rerank"],
        hybrid={"method": "weighted", "weights": {"vector": 1.0, "lexical": 3.0}},
        rerank={"enabled": True},
        max_results=3,
    )
    session = AsyncMock(spec=AsyncSession)

    response = await run_retrieval_debug(
        request,
        session=session,
        embedder=embedder,  # type: ignore[arg-type]
        repository=repository,  # type: ignore[arg-type]
        lexical_repository=lexical_repository,  # type: ignore[arg-type]
        reranker=_FakeFilterReranker(),
    )

    assert response.diff is not None
    assert [result.chunk_id for result in response.final_results] == [103, 102]
    assert [entry.chunk_id for entry in response.diff.dropped_by_rerank] == [101]


@pytest.mark.asyncio
async def test_run_retrieval_debug_hybrid_disabled_omits_hybrid_branch() -> None:
    embedder = _FakeEmbedder()
    repository = _FakeRepository(results=[_search_result(chunk_id=101, distance=0.2)])
    lexical_repository = _FakeLexicalRepository(
        results=[_lexical_result(chunk_id=201, ts_rank=0.8)]
    )
    request = RetrievalDebugRequest(
        query="OAuth2",
        strategies=["vector", "lexical", "hybrid"],
        hybrid={"enabled": False},
    )
    session = AsyncMock(spec=AsyncSession)

    response = await run_retrieval_debug(
        request,
        session=session,
        embedder=embedder,  # type: ignore[arg-type]
        repository=repository,  # type: ignore[arg-type]
        lexical_repository=lexical_repository,  # type: ignore[arg-type]
    )

    assert response.branches.hybrid is None
    assert [result.chunk_id for result in response.final_results] == [101]
    assert response.final_results[0].fusion_rank is None
    assert response.diff is None


@pytest.mark.asyncio
async def test_run_retrieval_debug_keeps_vector_results_when_lexical_branch_fails() -> None:
    embedder = _FakeEmbedder()
    repository = _FakeRepository(results=[_search_result(chunk_id=101, distance=0.2)])
    lexical_repository = _FakeLexicalRepository(error=RuntimeError("database unavailable"))
    request = RetrievalDebugRequest(query="OAuth2", strategies=["vector", "lexical"])
    session = AsyncMock(spec=AsyncSession)

    response = await run_retrieval_debug(
        request,
        session=session,
        embedder=embedder,  # type: ignore[arg-type]
        repository=repository,  # type: ignore[arg-type]
        lexical_repository=lexical_repository,  # type: ignore[arg-type]
    )

    assert response.branches.vector is not None
    assert response.branches.lexical is None
    assert [result.chunk_id for result in response.final_results] == [101]
    assert any("Lexical branch failed" in warning for warning in response.warnings)
