"""API-key auth tests for retrieval and RAG estimate endpoints (feature-056)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.database import get_db_session
from app.embedding_pipeline.rerank import NoOpReranker
from app.main import app
from app.middleware import security
from app.routers import rag_estimations, retrieval
from tests.embedding_pipeline.test_retrieval_router import (
    _FakeEmbedder,
    _FakeLexicalRepository,
    _FakeSession,
    _FakeVectorRepository,
)
from tests.test_rag_estimation_endpoint import _FakeRagService, _grounded_result, _outcome

RET_KEY = "retrieval-secret"
EST_KEY = "estimate-secret"

RETRIEVAL_PATH = "/api/v1/retrieval"
RAG_PATH = "/api/v1/estimate/rag"


def _settings_with_keys() -> Settings:
    return Settings(
        retrieval_api_key=RET_KEY,
        estimate_api_key=EST_KEY,
        rate_limit_enabled=False,
    )


@pytest.fixture(autouse=True)
def stub_downstream(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(security, "get_settings", _settings_with_keys)

    async def override_db():
        yield _FakeSession()

    app.dependency_overrides[get_db_session] = override_db
    app.dependency_overrides[retrieval.get_embedder] = lambda: _FakeEmbedder()  # type: ignore[assignment]
    app.dependency_overrides[retrieval.get_vector_repository] = lambda: _FakeVectorRepository()  # type: ignore[assignment]
    app.dependency_overrides[retrieval.get_lexical_repository] = lambda: _FakeLexicalRepository()  # type: ignore[assignment]
    app.dependency_overrides[retrieval.get_reranker] = lambda: NoOpReranker()  # type: ignore[assignment]
    app.dependency_overrides[rag_estimations.get_rag_estimation_service] = (  # type: ignore[assignment]
        lambda: _FakeRagService(_outcome(_grounded_result()))
    )
    yield
    app.dependency_overrides.clear()


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


_RETRIEVAL_BODY = {"query": "ecommerce storefront checkout"}
_RAG_BODY = {"question": "How long for OAuth integration?"}


def test_retrieval_requires_key_when_configured(client: TestClient) -> None:
    response = client.post(RETRIEVAL_PATH, json=_RETRIEVAL_BODY)
    assert response.status_code == 401


def test_retrieval_accepts_retrieval_key(client: TestClient) -> None:
    response = client.post(
        RETRIEVAL_PATH,
        json=_RETRIEVAL_BODY,
        headers={"X-API-Key": RET_KEY},
    )
    assert response.status_code == 200


def test_rag_estimate_requires_key_when_configured(client: TestClient) -> None:
    response = client.post(RAG_PATH, json=_RAG_BODY)
    assert response.status_code == 401


def test_rag_estimate_accepts_estimate_key(client: TestClient) -> None:
    response = client.post(RAG_PATH, json=_RAG_BODY, headers={"X-API-Key": EST_KEY})
    assert response.status_code == 200


def test_keys_are_independent(client: TestClient) -> None:
    rag_with_retrieval_key = client.post(
        RAG_PATH,
        json=_RAG_BODY,
        headers={"X-API-Key": RET_KEY},
    )
    retrieval_with_estimate_key = client.post(
        RETRIEVAL_PATH,
        json=_RETRIEVAL_BODY,
        headers={"X-API-Key": EST_KEY},
    )
    assert rag_with_retrieval_key.status_code == 401
    assert retrieval_with_estimate_key.status_code == 401


def test_wrong_key_is_rejected(client: TestClient) -> None:
    response = client.post(
        RETRIEVAL_PATH,
        json=_RETRIEVAL_BODY,
        headers={"X-API-Key": "nope"},
    )
    assert response.status_code == 401


def test_open_access_when_keys_unset(monkeypatch: pytest.MonkeyPatch, client: TestClient) -> None:
    monkeypatch.setattr(
        security,
        "get_settings",
        lambda: Settings(rate_limit_enabled=False),
    )
    response = client.post(RETRIEVAL_PATH, json=_RETRIEVAL_BODY)
    assert response.status_code == 200
