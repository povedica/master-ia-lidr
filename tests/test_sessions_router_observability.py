"""Langfuse trace wiring for session HTTP routes."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from app.config import Settings, get_settings
from app.main import app
from app.routers import sessions as sessions_router
from app.services.sessions import session_store


def _trace_cm(mock_obs: MagicMock) -> MagicMock:
    cm = MagicMock()
    cm.__enter__ = MagicMock(return_value=None)
    cm.__exit__ = MagicMock(return_value=False)
    mock_obs.start_trace.return_value = cm
    span_cm = MagicMock()
    span_cm.__enter__ = MagicMock(return_value=None)
    span_cm.__exit__ = MagicMock(return_value=False)
    mock_obs.start_span.return_value = span_cm
    return cm


def test_session_create_starts_trace() -> None:
    mock_obs = MagicMock()
    _trace_cm(mock_obs)
    app.dependency_overrides[get_settings] = lambda: Settings(openai_api_key="sk-test")
    try:
        with patch.object(session_store, "_sessions", {}), patch(
            "app.routers.sessions.get_observability",
            return_value=mock_obs,
        ):
            with TestClient(app) as client:
                response = client.post("/api/v1/sessions")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 201
    mock_obs.start_trace.assert_called()
    assert mock_obs.start_trace.call_args.args[0] == sessions_router.SESSION_CREATE_TRACE


def test_session_list_starts_trace() -> None:
    mock_obs = MagicMock()
    _trace_cm(mock_obs)
    app.dependency_overrides[get_settings] = lambda: Settings(openai_api_key="sk-test")
    try:
        with patch(
            "app.routers.sessions.get_observability",
            return_value=mock_obs,
        ):
            with TestClient(app) as client:
                response = client.get("/api/v1/sessions")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert mock_obs.start_trace.call_args.args[0] == sessions_router.SESSION_LIST_TRACE
