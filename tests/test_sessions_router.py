"""Integration tests for session HTTP routes."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.config import Settings, get_settings
from app.guardrails.contracts import FinalResponseStatus
from app.guardrails.llm_pipeline import StructuredPipelineOutcome
from app.routers.sessions import get_session_estimation_service, router
from app.schemas.estimation_request import EstimationRequest
from app.services.estimation_engine import EstimationMode, InputAssessment, ModeEligibility
from app.services.llm_service import StructuredEstimateBundle, UsageInfo
from app.services.session_estimation_service import SessionNotFoundError, SessionSubmitOutcome
from app.services.sessions import InMemorySessionStore, Session
from tests.estimation_fixtures import minimal_estimation_request_dict

from app.schemas.estimation_result import EstimationLineItem, EstimationResult, EstimationTotals


def _build_app(store: InMemorySessionStore) -> FastAPI:
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")

    settings = Settings(openai_api_key="test-key", llm_domain_guardrail_enabled=False)

    def override_settings() -> Settings:
        return settings

    fake_estimation = MagicMock()
    fake_estimation._providers = []
    service = MagicMock()

    app.dependency_overrides[get_settings] = override_settings
    app.dependency_overrides[get_session_estimation_service] = lambda: service
    app.state._test_store = store  # type: ignore[attr-defined]
    app.state._test_service = service  # type: ignore[attr-defined]
    return app


def _bundle() -> StructuredEstimateBundle:
    li = EstimationLineItem(name="Task", hours=1.0, cost_eur=50.0)
    totals = EstimationTotals(hours=1.0, cost_eur=50.0)
    result = EstimationResult(
        title="Estimate",
        summary="S" * 25,
        phases=[],
        line_items=[li],
        totals=totals,
        duration_weeks=1.0,
        confidence=0.8,
    )
    return StructuredEstimateBundle(
        result=result,
        prompt_version="estimation/v2",
        examples_version="ex",
        mode=EstimationMode.STANDARD,
        model="gpt-4o-mini",
        provider="openai",
        usage=UsageInfo(prompt_tokens=1, completion_tokens=1, total_tokens=2),
        degraded=False,
        finish_reason="stop",
        assessment=InputAssessment(
            detail_level="medium",
            recommended_mode=EstimationMode.STANDARD,
            reason="fixture",
        ),
        mode_eligibility=ModeEligibility(
            allowed_modes=(EstimationMode.STANDARD,),
            blocked_modes=(),
            reason=None,
        ),
    )


def _submit_outcome(session: Session) -> SessionSubmitOutcome:
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


def test_list_sessions_returns_empty_when_store_empty() -> None:
    store = InMemorySessionStore()
    with patch("app.routers.sessions.session_store", store):
        client = TestClient(_build_app(store))
        response = client.get("/api/v1/sessions")

    assert response.status_code == 200
    assert response.json() == []


def test_list_sessions_returns_summaries_ordered_by_activity() -> None:
    store = InMemorySessionStore()
    first = store.create_session()
    second = store.create_session()
    second.submit_count = 2
    with patch("app.routers.sessions.session_store", store):
        client = TestClient(_build_app(store))
        response = client.get("/api/v1/sessions")

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 2
    assert body[0]["session_id"] == second.session_id
    assert body[0]["submit_count"] == 2


def test_create_session_returns_distinct_ids() -> None:
    store = InMemorySessionStore()
    with patch("app.routers.sessions.session_store", store):
        client = TestClient(_build_app(store))
        first = client.post("/api/v1/sessions")
        second = client.post("/api/v1/sessions")

    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["session_id"] != second.json()["session_id"]


def test_estimate_in_session_returns_structured_response() -> None:
    store = InMemorySessionStore()
    session = store.create_session()
    app = _build_app(store)
    service = app.dependency_overrides[get_session_estimation_service]()
    service.run_submit = AsyncMock(return_value=_submit_outcome(session))

    with patch("app.routers.sessions.session_store", store):
        client = TestClient(app)
        response = client.post(
            f"/api/v1/sessions/{session.session_id}/estimate",
            json=minimal_estimation_request_dict(),
        )

    assert response.status_code == 200
    assert response.json()["result"]["title"] == "Estimate"


def test_estimate_unknown_session_returns_404() -> None:
    store = InMemorySessionStore()
    app = _build_app(store)
    service = app.dependency_overrides[get_session_estimation_service]()
    service.run_submit = AsyncMock(side_effect=SessionNotFoundError("missing"))

    with patch("app.routers.sessions.session_store", store):
        client = TestClient(app)
        response = client.post(
            "/api/v1/sessions/missing/estimate",
            json=minimal_estimation_request_dict(),
        )

    assert response.status_code == 404


def test_estimate_rejects_free_text_body() -> None:
    store = InMemorySessionStore()
    session = store.create_session()
    with patch("app.routers.sessions.session_store", store):
        client = TestClient(_build_app(store))
        response = client.post(
            f"/api/v1/sessions/{session.session_id}/estimate",
            json={"user_message": "hello"},
        )

    assert response.status_code == 422
