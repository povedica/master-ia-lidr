"""Integration test: runtime retrieval config overrides POST /api/v1/retrieval (feature-057)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.config import Settings, get_settings
from app.embedding_pipeline.retrieval_service import (
    _NOOP_RERANK_WARNING,
    _RERANK_DISABLED_WARNING,
)
from app.main import app
from app.routers import retrieval, runtime_config
from tests.embedding_pipeline.test_retrieval_router import (
    _FakeEmbedder,
    _FakeLexicalRepository,
    _FakeSession,
    _FakeVectorRepository,
)
from tests.test_runtime_config import _FakeRedis

RETRIEVAL_PATH = "/api/v1/retrieval"
CONFIG_PATH = "/api/v1/config/retrieval"


@pytest.fixture(autouse=True)
def stub_downstream() -> None:
    async def override_db():
        yield _FakeSession()

    app.dependency_overrides[retrieval.get_db_session] = override_db
    app.dependency_overrides[retrieval.get_embedder] = lambda: _FakeEmbedder()  # type: ignore[assignment]
    app.dependency_overrides[retrieval.get_vector_repository] = lambda: _FakeVectorRepository()  # type: ignore[assignment]
    app.dependency_overrides[retrieval.get_lexical_repository] = lambda: _FakeLexicalRepository()  # type: ignore[assignment]
    yield
    app.dependency_overrides.clear()


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def _settings_with_rerank_enabled() -> Settings:
    # No rerank model configured: NoOpReranker builds either way, so any
    # degradation warning we see is driven purely by the *effective*
    # rerank_enabled flag, not by reranker availability.
    return Settings(
        _env_file=None,
        retrieval_rerank_enabled=True,
        rate_limit_enabled=False,
    )


def test_mode_c_without_override_hits_noop_rerank_warning(client: TestClient) -> None:
    app.dependency_overrides[get_settings] = _settings_with_rerank_enabled
    app.dependency_overrides[runtime_config.get_runtime_redis_client] = lambda: None

    response = client.post(RETRIEVAL_PATH, json={"query": "OAuth backend", "mode": "C"})

    assert response.status_code == 200
    assert _NOOP_RERANK_WARNING in response.json()["warnings"]
    assert _RERANK_DISABLED_WARNING not in response.json()["warnings"]


def test_mode_c_after_runtime_override_disables_rerank(client: TestClient) -> None:
    app.dependency_overrides[get_settings] = _settings_with_rerank_enabled
    fake_redis = _FakeRedis()
    app.dependency_overrides[runtime_config.get_runtime_redis_client] = lambda: fake_redis

    put_response = client.put(CONFIG_PATH, json={"rerank_enabled": False})
    assert put_response.status_code == 200
    assert put_response.json()["rerank_enabled"] is False

    response = client.post(RETRIEVAL_PATH, json={"query": "OAuth backend", "mode": "C"})

    assert response.status_code == 200
    body = response.json()
    assert _RERANK_DISABLED_WARNING in body["warnings"]
    assert body["mode"] == "A"
