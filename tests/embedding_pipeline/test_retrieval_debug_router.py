"""Integration tests for retrieval debug HTTP endpoints (feature-042)."""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
from fastapi import HTTPException, status
from fastapi.testclient import TestClient

from app.embedding_pipeline.retrieval_debug_schemas import ChunkInspectionResponse
from app.embedding_pipeline.schemas import SearchResult
from app.main import app
from app.routers import retrieval_debug

POST_PATH = "/api/v1/retrieval-debug"
CHUNK_PATH = "/api/v1/retrieval-debug/chunks/156"
EMBEDDING_DIM = 1536


def _make_vector(seed: float = 0.1) -> list[float]:
    return [seed + i * 0.0001 for i in range(EMBEDDING_DIM)]


class _FakeEmbedder:
    def __init__(self) -> None:
        self.embed_one_calls = 0
        self.last_query: str | None = None

    async def embed_one(self, text: str) -> list[float]:
        self.embed_one_calls += 1
        self.last_query = text
        return _make_vector()


class _FakeSearchRepository:
    def __init__(self) -> None:
        self.last_k: int | None = None

    async def search_chunks(self, session: object, *, query_vector: list[float], k: int) -> list[SearchResult]:
        del session, query_vector
        self.last_k = k
        return [
            SearchResult(
                chunk_id=156,
                document_id=12,
                chunk_type="budget_component",
                content="Backend OAuth implementation",
                distance=0.231,
                metadata={"budget_id": "BUD-2024-014", "component_id": "AUTH-001"},
            )
        ]


class _FakeChunkRepository:
    def __init__(self) -> None:
        self.distance_calls = 0

    async def get_chunk_inspection(
        self,
        session: object,
        *,
        chunk_id: int,
        embedding_model: str,
    ) -> ChunkInspectionResponse | None:
        del session
        if chunk_id != 156:
            return None
        return ChunkInspectionResponse(
            chunk_id=156,
            document_id=12,
            content="Backend OAuth implementation",
            chunk_type="budget_component",
            metadata={"component_id": "AUTH-001"},
            embedding_model=embedding_model,
            embedding_present=True,
            document={
                "id": 12,
                "source_path": "data/budgets/example.json",
                "document_type": "historical_budget",
                "metadata": {"budget_id": "BUD-2024-014"},
            },
            previous_chunk={"chunk_id": 155, "content_excerpt": "Previous context"},
            next_chunk={"chunk_id": 157, "content_excerpt": "Next context"},
        )

    async def get_chunk_distance(
        self,
        session: object,
        *,
        chunk_id: int,
        query_vector: list[float],
    ) -> float | None:
        del session, query_vector
        self.distance_calls += 1
        if chunk_id != 156:
            return None
        return 0.25


class _FakeSession:
    async def close(self) -> None:
        return None


@pytest.fixture
def retrieval_debug_client() -> TestClient:
    fake_embedder = _FakeEmbedder()
    search_repository = _FakeSearchRepository()
    chunk_repository = _FakeChunkRepository()
    fake_session = _FakeSession()

    async def _session_override() -> AsyncIterator[_FakeSession]:
        yield fake_session

    app.dependency_overrides[retrieval_debug.get_db_session] = _session_override
    app.dependency_overrides[retrieval_debug.get_embedder] = lambda: fake_embedder  # type: ignore[return-value]
    app.dependency_overrides[retrieval_debug.get_search_repository] = lambda: search_repository  # type: ignore[return-value]
    app.dependency_overrides[retrieval_debug.get_retrieval_debug_repository] = lambda: chunk_repository  # type: ignore[return-value]
    try:
        with TestClient(app) as test_client:
            test_client.fake_embedder = fake_embedder  # type: ignore[attr-defined]
            test_client.search_repository = search_repository  # type: ignore[attr-defined]
            test_client.chunk_repository = chunk_repository  # type: ignore[attr-defined]
            yield test_client
    finally:
        app.dependency_overrides.clear()


def test_openapi_lists_retrieval_debug_routes() -> None:
    schema = app.openapi()
    assert POST_PATH in schema["paths"]
    assert "/api/v1/retrieval-debug/chunks/{chunk_id}" in schema["paths"]


def test_post_retrieval_debug_returns_vector_trace(retrieval_debug_client: TestClient) -> None:
    response = retrieval_debug_client.post(
        POST_PATH,
        json={"query": "OAuth backend", "strategies": ["vector"], "vector": {"top_k": 5}},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["branches"]["vector"][0]["chunk_id"] == 156
    assert body["final_results"][0]["semantic_distance"] == pytest.approx(0.231)
    assert body["branches"]["lexical"] is None
    assert retrieval_debug_client.fake_embedder.embed_one_calls == 1  # type: ignore[attr-defined]
    assert retrieval_debug_client.search_repository.last_k == 5  # type: ignore[attr-defined]


def test_post_retrieval_debug_logs_safe_completion(
    retrieval_debug_client: TestClient,
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level("INFO"):
        response = retrieval_debug_client.post(POST_PATH, json={"query": "OAuth backend"})

    assert response.status_code == 200
    assert any(
        record.message == "retrieval_debug_completed"
        and getattr(record, "request_id", "").startswith("rdbg_")
        and getattr(record, "strategies", None) == ["vector"]
        and getattr(record, "vector_result_count", None) == 1
        and getattr(record, "lexical_result_count", None) == 0
        and getattr(record, "max_results", None) == 10
        and isinstance(getattr(record, "timings_ms", None), dict)
        for record in caplog.records
    )


def test_post_retrieval_debug_database_not_configured_returns_503() -> None:
    async def _missing_db_override() -> AsyncIterator[None]:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database is not configured.",
        )
        yield None

    app.dependency_overrides[retrieval_debug.get_db_session] = _missing_db_override
    try:
        with TestClient(app) as test_client:
            response = test_client.post(POST_PATH, json={"query": "OAuth backend"})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 503
    assert response.json()["detail"] == "Database is not configured."


def test_chunk_inspector_returns_context_and_optional_similarity(
    retrieval_debug_client: TestClient,
) -> None:
    response = retrieval_debug_client.get(f"{CHUNK_PATH}?query=OAuth backend")

    assert response.status_code == 200
    body = response.json()
    assert body["chunk_id"] == 156
    assert body["previous_chunk"]["chunk_id"] == 155
    assert body["next_chunk"]["chunk_id"] == 157
    assert body["distance"] == pytest.approx(0.25)
    assert body["similarity"] == pytest.approx(0.75)
    assert retrieval_debug_client.fake_embedder.embed_one_calls == 1  # type: ignore[attr-defined]
    assert retrieval_debug_client.chunk_repository.distance_calls == 1  # type: ignore[attr-defined]


def test_chunk_inspector_unknown_chunk_returns_404(retrieval_debug_client: TestClient) -> None:
    response = retrieval_debug_client.get("/api/v1/retrieval-debug/chunks/999")

    assert response.status_code == 404
    assert response.json()["detail"] == "Chunk not found."
