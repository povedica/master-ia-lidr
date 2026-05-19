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


def test_list_sessions_returns_recent_sessions() -> None:
    from unittest.mock import patch

    store = InMemorySessionStore()
    with patch("app.routers.sessions.session_store", store):
        client = TestClient(_build_app(store))
        created = client.post("/api/v1/sessions")
        session_id = created.json()["session_id"]
        session = store.get_session(session_id)
        assert session is not None
        session.submit_count = 1
        session.last_normalized_payload = {"project_name": "NeoBank Mobile"}
        listed = client.get("/api/v1/sessions")

    assert listed.status_code == 200
    body = listed.json()
    assert len(body["sessions"]) == 1
    assert body["sessions"][0]["session_id"] == session_id
    assert body["sessions"][0]["label"] == "NeoBank Mobile"
    assert body["sessions"][0]["submit_count"] == 1


def test_get_session_returns_snapshot_and_404() -> None:
    from unittest.mock import patch

    from app.services.sessions import DerivedProjectMetadata
    from app.schemas.estimation_request import ProjectType, TargetAudience

    store = InMemorySessionStore()
    with patch("app.routers.sessions.session_store", store):
        client = TestClient(_build_app(store))
        created = client.post("/api/v1/sessions")
        session_id = created.json()["session_id"]
        session = store.get_session(session_id)
        assert session is not None
        session.last_normalized_payload = {
            "project_name": "Alpha",
            "transcript": "x" * 80,
            "project_type": "web_saas",
            "target_audience": "b2b_enterprise",
        }
        session.last_derived_metadata = DerivedProjectMetadata(
            project_name="Alpha",
            project_type=ProjectType.web_saas,
            target_audience=TargetAudience.b2b_enterprise,
        )
        session.last_estimate = {"result": {"title": "Alpha estimate", "summary": "x" * 25}}
        session.last_warnings = ["industry not provided"]
        session.last_attachment_statuses = [
            {
                "file_id": "f1",
                "name": "notes.txt",
                "mime_type": "text/plain",
                "status": "processed",
            }
        ]
        detail = client.get(f"/api/v1/sessions/{session_id}")
        missing = client.get("/api/v1/sessions/does-not-exist")

    assert detail.status_code == 200
    assert detail.json()["input_payload"]["project_name"] == "Alpha"
    assert detail.json()["project_metadata"]["project_name"] == "Alpha"
    assert detail.json()["estimate"]["result"]["title"] == "Alpha estimate"
    assert detail.json()["warnings"] == ["industry not provided"]
    assert detail.json()["attachments"][0]["name"] == "notes.txt"
    assert missing.status_code == 404
