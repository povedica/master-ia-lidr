"""API tests for GET/PUT /api/v1/config/models and /api/v1/config/retrieval (feature-057)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.config import Settings, get_settings
from app.main import app
from app.routers import runtime_config
from tests.test_runtime_config import _FailingRedis, _FakeRedis

RETRIEVAL_PATH = "/api/v1/config/retrieval"
MODELS_PATH = "/api/v1/config/models"


@pytest.fixture(autouse=True)
def _clear_overrides() -> None:
    yield
    app.dependency_overrides.clear()


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def _use_settings(settings: Settings) -> None:
    app.dependency_overrides[get_settings] = lambda: settings


def _use_redis(redis_client: object | None) -> None:
    app.dependency_overrides[runtime_config.get_runtime_redis_client] = lambda: redis_client


def test_get_retrieval_config_returns_settings_defaults_without_redis(
    client: TestClient,
) -> None:
    _use_settings(
        Settings(
            _env_file=None,
            retrieval_rerank_enabled=True,
            retrieval_recall_k=33,
        )
    )
    _use_redis(None)

    response = client.get(RETRIEVAL_PATH)

    assert response.status_code == 200
    body = response.json()
    assert body["rerank_enabled"] is True
    assert body["recall_k"] == 33


def test_put_then_get_retrieval_config_round_trips_through_redis(client: TestClient) -> None:
    _use_settings(Settings(_env_file=None, retrieval_rerank_enabled=True))
    fake_redis = _FakeRedis()
    _use_redis(fake_redis)

    put_response = client.put(RETRIEVAL_PATH, json={"rerank_enabled": False})
    assert put_response.status_code == 200
    assert put_response.json()["rerank_enabled"] is False

    get_response = client.get(RETRIEVAL_PATH)
    assert get_response.status_code == 200
    assert get_response.json()["rerank_enabled"] is False


def test_put_retrieval_config_invalid_body_returns_422(client: TestClient) -> None:
    _use_settings(Settings(_env_file=None))
    _use_redis(_FakeRedis())

    response = client.put(RETRIEVAL_PATH, json={"recall_k": 0})

    assert response.status_code == 422


def test_put_retrieval_config_returns_503_without_redis(client: TestClient) -> None:
    _use_settings(Settings(_env_file=None))
    _use_redis(None)

    response = client.put(RETRIEVAL_PATH, json={"rerank_enabled": False})

    assert response.status_code == 503


def test_put_retrieval_config_returns_503_when_redis_write_fails(client: TestClient) -> None:
    _use_settings(Settings(_env_file=None))
    _use_redis(_FailingRedis())

    response = client.put(RETRIEVAL_PATH, json={"rerank_enabled": False})

    assert response.status_code == 503


def test_get_models_config_returns_settings_defaults_without_redis(client: TestClient) -> None:
    _use_settings(
        Settings(_env_file=None, openai_model="gpt-4o-mini", ragas_judge_model="gpt-4o-mini")
    )
    _use_redis(None)

    response = client.get(MODELS_PATH)

    assert response.status_code == 200
    body = response.json()
    assert body["structured_model"] == "gpt-4o-mini"
    assert body["judge_model"] == "gpt-4o-mini"


def test_put_then_get_models_config_round_trips_through_redis(client: TestClient) -> None:
    _use_settings(
        Settings(_env_file=None, openai_model="gpt-4o-mini", ragas_judge_model="gpt-4o-mini")
    )
    fake_redis = _FakeRedis()
    _use_redis(fake_redis)

    put_response = client.put(MODELS_PATH, json={"structured_model": "gpt-4.1-mini"})
    assert put_response.status_code == 200
    assert put_response.json()["structured_model"] == "gpt-4.1-mini"

    get_response = client.get(MODELS_PATH)
    assert get_response.status_code == 200
    body = get_response.json()
    assert body["structured_model"] == "gpt-4.1-mini"
    assert body["judge_model"] == "gpt-4o-mini"


def test_openapi_lists_config_routes() -> None:
    schema = app.openapi()
    assert RETRIEVAL_PATH in schema["paths"]
    assert MODELS_PATH in schema["paths"]
