"""Integration tests for POST /api/v1/retrieval (feature-050)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.config import Settings, get_settings
from app.embedding_pipeline.lexical_search_repository import LexicalSearchResult
from app.embedding_pipeline.rerank import NoOpReranker
from app.embedding_pipeline.schemas import SearchResult
from app.main import app
from app.routers import retrieval

RETRIEVAL_PATH = "/api/v1/retrieval"
EMBEDDING_DIM = 1536


def _make_vector(seed: float = 0.1) -> list[float]:
    return [seed + i * 0.0001 for i in range(EMBEDDING_DIM)]


class _FakeEmbedder:
    async def embed_one(self, text: str) -> list[float]:
        del text
        return _make_vector()


class _FakeVectorRepository:
    async def search_chunks(self, session, *, query_vector, k):
        del session, query_vector, k
        return [
            SearchResult(
                chunk_id=156,
                document_id=12,
                chunk_type="budget_component",
                content="Backend OAuth implementation",
                distance=0.231,
                metadata={"budget_id": "BUD-2024-014", "scope": "backend"},
            )
        ]


class _FakeLexicalRepository:
    async def search_chunks(self, session, *, query, top_k):
        del session, query, top_k
        return [
            LexicalSearchResult(
                chunk_id=156,
                document_id=12,
                chunk_type="budget_component",
                content="Backend OAuth implementation",
                metadata={"budget_id": "BUD-2024-014", "scope": "backend"},
                ts_rank=0.8,
                matched_terms=["oauth"],
            )
        ]


class _FakeSession:
    async def close(self) -> None:
        return None


@pytest.fixture
def retrieval_client() -> TestClient:
    fake_session = _FakeSession()

    async def _session_override():
        yield fake_session

    app.dependency_overrides[retrieval.get_db_session] = _session_override
    app.dependency_overrides[retrieval.get_embedder] = lambda: _FakeEmbedder()  # type: ignore[return-value]
    app.dependency_overrides[retrieval.get_vector_repository] = lambda: _FakeVectorRepository()  # type: ignore[return-value]
    app.dependency_overrides[retrieval.get_lexical_repository] = lambda: _FakeLexicalRepository()  # type: ignore[return-value]
    app.dependency_overrides[retrieval.get_reranker] = lambda: NoOpReranker()  # type: ignore[return-value]
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()


def test_openapi_lists_retrieval_route() -> None:
    schema = app.openapi()
    assert RETRIEVAL_PATH in schema["paths"]


def test_retrieval_mode_a_contract(retrieval_client: TestClient) -> None:
    response = retrieval_client.post(
        RETRIEVAL_PATH,
        json={"query": "OAuth backend", "mode": "A"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["mode"] == "A"
    assert body["applied_config"]["branches"] == ["vector"]
    assert body["results"][0]["chunk_id"] == 156
    assert body["results"][0]["budget_id"] == "BUD-2024-014"


def test_retrieval_empty_database_url_returns_503(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "")
    get_settings.cache_clear()
    try:
        with TestClient(app) as client:
            response = client.post(
                RETRIEVAL_PATH,
                json={"query": "OAuth backend", "mode": "A"},
            )
    finally:
        get_settings.cache_clear()

    assert response.status_code == 503
    assert response.json()["detail"] == "Database is not configured."
