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


def test_session_estimate_trace_uses_store_session_id() -> None:
    from datetime import UTC, datetime

    from app.guardrails.contracts import FinalResponseStatus
    from app.guardrails.llm_pipeline import StructuredPipelineOutcome
    from app.services.estimation_v2_response_builder import assemble_estimation_v2_response
    from app.services.session_estimation_service import SessionSubmitOutcome
    from app.services.sessions import Session
    from tests.estimation_fixtures import minimal_estimation_request_dict
    from tests.test_sessions_router import _bundle

    mock_obs = MagicMock()
    _trace_cm(mock_obs)
    store_session_id = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"

    class _FakeSubmitService:
        async def run_submit(self, session_id: str, request: object, *, request_id: str):
            del request, request_id
            session = Session(session_id=session_id)
            return SessionSubmitOutcome(
                session=session,
                pipeline=StructuredPipelineOutcome(
                    bundle=_bundle(),
                    final_status=FinalResponseStatus.SUCCESS,
                    reason_code=None,
                    user_message=None,
                    technical_message=None,
                    audit_id="audit",
                    safe_to_cache=True,
                    safe_to_display=True,
                ),
            )

    app.dependency_overrides[get_settings] = lambda: Settings(openai_api_key="sk-test", dev_mode=False)
    app.dependency_overrides[sessions_router.get_session_estimation_service] = (
        lambda: _FakeSubmitService()  # type: ignore[return-value]
    )
    try:
        with patch("app.routers.sessions.get_observability", return_value=mock_obs):
            with TestClient(app) as client:
                response = client.post(
                    f"/api/v1/sessions/{store_session_id}/estimate",
                    json=minimal_estimation_request_dict(),
                )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    ctx = mock_obs.start_trace.call_args.kwargs["context"]
    assert ctx.session_id == store_session_id
    assert mock_obs.start_trace.call_args.args[0] == sessions_router.SESSION_ESTIMATE_TRACE
    _ = assemble_estimation_v2_response  # import used by router at runtime
