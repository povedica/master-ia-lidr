"""Rate-limiting tests for RAG estimate endpoint (feature-056)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.database import get_db_session
from app.main import app
from app.middleware import rate_limiting, security
from app.routers import rag_estimations
from tests.test_rag_estimation_endpoint import _FakeRagService, _grounded_result, _outcome

_LIMIT_KEY = "ratelimit-estimate-key"
RAG_PATH = "/api/v1/estimate/rag"
_BODY = {"question": "How long for OAuth integration?"}


class _FakeSession:
    async def close(self) -> None:
        return None


@pytest.fixture(autouse=True)
def stub_downstream(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        security,
        "get_settings",
        lambda: Settings(
            retrieval_api_key="retrieval",
            estimate_api_key=_LIMIT_KEY,
            rate_limit_enabled=True,
        ),
    )
    monkeypatch.setattr(
        rate_limiting,
        "get_settings",
        lambda: Settings(
            retrieval_api_key="retrieval",
            estimate_api_key=_LIMIT_KEY,
            rate_limit_enabled=True,
        ),
    )

    async def override_db():
        yield _FakeSession()

    app.dependency_overrides[get_db_session] = override_db
    app.dependency_overrides[rag_estimations.get_rag_estimation_service] = (  # type: ignore[assignment]
        lambda: _FakeRagService(_outcome(_grounded_result()))
    )
    yield
    app.dependency_overrides.clear()


def test_rag_estimate_returns_429_with_retry_after_when_limit_exceeded() -> None:
    client = TestClient(app)
    headers = {"X-API-Key": _LIMIT_KEY}

    statuses = [
        client.post(RAG_PATH, json=_BODY, headers=headers).status_code for _ in range(11)
    ]

    assert statuses[:10] == [200] * 10
    blocked = client.post(RAG_PATH, json=_BODY, headers=headers)
    assert blocked.status_code == 429
    assert blocked.headers.get("Retry-After") == "60"
    body = blocked.json()
    assert body["retry_after_seconds"] == 60
