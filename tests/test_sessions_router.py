"""Integration tests for session HTTP routes (simplified contract)."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.config import Settings, get_settings
from app.routers.sessions import router
from app.services.sessions import InMemorySessionStore


def _build_app(store: InMemorySessionStore) -> FastAPI:
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    settings = Settings(openai_api_key="test-key", llm_domain_guardrail_enabled=False)
    app.dependency_overrides[get_settings] = lambda: settings
    return app


def test_create_session_returns_distinct_ids() -> None:
    from unittest.mock import patch

    store = InMemorySessionStore()
    with patch("app.routers.sessions.session_store", store):
        client = TestClient(_build_app(store))
        first = client.post("/api/v1/sessions")
        second = client.post("/api/v1/sessions")

    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["session_id"] != second.json()["session_id"]
