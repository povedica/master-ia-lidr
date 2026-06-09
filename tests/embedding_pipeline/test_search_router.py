"""Integration tests for POST /api/v1/search (feature-038)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.embedding_pipeline.schemas import SearchRequest, SearchResponse, SearchResult
from app.main import app
from app.routers import search

SEARCH_PATH = "/api/v1/search"
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


class _FailingEmbedder:
    async def embed_one(self, text: str) -> list[float]:
        del text
        raise RuntimeError("OpenAI API key is not configured.")


class _FakeRepository:
    def __init__(self, results: list[SearchResult] | None = None) -> None:
        self.results = results or []
        self.last_k: int | None = None

    async def search_chunks(self, session: object, *, query_vector: list[float], k: int) -> list[SearchResult]:
        del session, query_vector
        self.last_k = k
        return self.results[:k]


class _FakeSession:
    async def close(self) -> None:
        return None


@pytest.fixture
def search_client() -> TestClient:
    fake_embedder = _FakeEmbedder()
    fake_repository = _FakeRepository(
        results=[
            SearchResult(
                chunk_id=156,
                document_id=12,
                chunk_type="budget_component",
                content="Backend OAuth implementation",
                distance=0.231,
                metadata={"scope": "backend"},
            )
        ]
    )
    fake_session = _FakeSession()

    async def _session_override():
        yield fake_session

    app.dependency_overrides[search.get_db_session] = _session_override
    app.dependency_overrides[search.get_embedder] = lambda: fake_embedder  # type: ignore[return-value]
    app.dependency_overrides[search.get_search_repository] = lambda: fake_repository  # type: ignore[return-value]
    try:
        with TestClient(app) as test_client:
            test_client.fake_embedder = fake_embedder  # type: ignore[attr-defined]
            test_client.fake_repository = fake_repository  # type: ignore[attr-defined]
            yield test_client
    finally:
        app.dependency_overrides.clear()


def test_openapi_lists_search_route() -> None:
    schema = app.openapi()
    assert SEARCH_PATH in schema["paths"]
    assert "post" in schema["paths"][SEARCH_PATH]


def test_search_returns_ranked_results(search_client: TestClient) -> None:
    response = search_client.post(
        SEARCH_PATH,
        json={"query": "REST API with OAuth authentication for fintech sector", "k": 5},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["query"] == "REST API with OAuth authentication for fintech sector"
    assert body["k"] == 5
    assert "search_time_ms" in body
    assert len(body["results"]) == 1
    result = body["results"][0]
    assert result["chunk_id"] == 156
    assert result["document_id"] == 12
    assert result["chunk_type"] == "budget_component"
    assert result["content"] == "Backend OAuth implementation"
    assert result["distance"] == pytest.approx(0.231)
    assert result["metadata"]["scope"] == "backend"
    assert search_client.fake_embedder.embed_one_calls == 1  # type: ignore[attr-defined]


def test_search_empty_corpus_returns_empty_results(search_client: TestClient) -> None:
    search_client.fake_repository.results = []  # type: ignore[attr-defined]
    response = search_client.post(SEARCH_PATH, json={"query": "anything", "k": 5})
    assert response.status_code == 200
    assert response.json()["results"] == []


def test_search_invalid_query_returns_422(search_client: TestClient) -> None:
    response = search_client.post(SEARCH_PATH, json={"query": "   ", "k": 5})
    assert response.status_code == 422


def test_search_invalid_k_returns_422(search_client: TestClient) -> None:
    response = search_client.post(SEARCH_PATH, json={"query": "valid query", "k": 0})
    assert response.status_code == 422


def test_search_embedder_failure_returns_safe_500_and_logs(
    caplog: pytest.LogCaptureFixture,
) -> None:
    fake_session = _FakeSession()

    async def _session_override():
        yield fake_session

    app.dependency_overrides[search.get_db_session] = _session_override
    app.dependency_overrides[search.get_embedder] = lambda: _FailingEmbedder()  # type: ignore[return-value]
    app.dependency_overrides[search.get_search_repository] = lambda: _FakeRepository()  # type: ignore[return-value]
    try:
        with TestClient(app) as test_client:
            with caplog.at_level("ERROR"):
                response = test_client.post(SEARCH_PATH, json={"query": "OAuth backend", "k": 3})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 500
    assert response.json()["detail"] == "Unable to complete semantic search."
    assert "OpenAI API key" not in response.text
    assert any(
        record.message == "semantic_search_failed"
        and getattr(record, "k", None) == 3
        and getattr(record, "error_type", "") == "RuntimeError"
        for record in caplog.records
    )
