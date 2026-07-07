"""API tests for POST /api/v1/retrieval/advanced (feature-061 Step 4)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.config import Settings, get_settings
from app.embedding_pipeline.lexical_search_repository import LexicalSearchResult
from app.embedding_pipeline.rerank import NoOpReranker
from app.embedding_pipeline.schemas import SearchResult
from app.main import app
from app.routers import retrieval_advanced

ADVANCED_PATH = "/api/v1/retrieval/advanced"
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
def advanced_client() -> TestClient:
    fake_session = _FakeSession()

    async def _session_override():
        yield fake_session

    app.dependency_overrides[retrieval_advanced.get_db_session] = _session_override
    app.dependency_overrides[retrieval_advanced.get_embedder] = lambda: _FakeEmbedder()  # type: ignore[return-value]
    app.dependency_overrides[retrieval_advanced.get_vector_repository] = (  # type: ignore[assignment]
        lambda: _FakeVectorRepository()
    )
    app.dependency_overrides[retrieval_advanced.get_lexical_repository] = (  # type: ignore[assignment]
        lambda: _FakeLexicalRepository()
    )
    app.dependency_overrides[retrieval_advanced.get_reranker] = lambda: NoOpReranker()  # type: ignore[assignment]
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()


def test_openapi_lists_advanced_retrieval_route() -> None:
    schema = app.openapi()
    assert ADVANCED_PATH in schema["paths"]


def test_advanced_retrieval_preset_a_returns_collection(advanced_client: TestClient) -> None:
    response = advanced_client.post(
        ADVANCED_PATH,
        json={"query": "OAuth backend", "preset": "A"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["config"]["search_mode"] == "vector"
    assert body["results"][0]["chunk_id"] == 156
    assert body["results"][0]["collection"] == "budgets"
    assert body["results"][0]["budget_id"] == "BUD-2024-014"


def test_advanced_retrieval_accepts_explicit_stage_config(advanced_client: TestClient) -> None:
    response = advanced_client.post(
        ADVANCED_PATH,
        json={
            "query": "OAuth backend",
            "config": {
                "search_mode": "hybrid",
                "rerank": False,
                "fusion": "rrf",
            },
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["config"]["search_mode"] == "hybrid"
    assert body["results"][0]["fusion_score"] is not None


def test_advanced_retrieval_rejects_preset_and_config_together(
    advanced_client: TestClient,
) -> None:
    response = advanced_client.post(
        ADVANCED_PATH,
        json={
            "query": "OAuth backend",
            "preset": "A",
            "config": {"search_mode": "vector"},
        },
    )
    assert response.status_code == 422


def test_advanced_retrieval_empty_database_url_returns_503(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DATABASE_URL", "")
    get_settings.cache_clear()
    try:
        with TestClient(app) as client:
            response = client.post(
                ADVANCED_PATH,
                json={"query": "OAuth backend", "preset": "A"},
            )
    finally:
        get_settings.cache_clear()

    assert response.status_code == 503
    assert response.json()["detail"] == "Database is not configured."
