"""Integration tests for session HTTP routes."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.config import Settings, get_settings
from app.routers.sessions import get_conversational_service, router
from app.services.conversational_estimation_service import (
    ConversationalEstimationService,
    SessionEstimateOutcome,
    SessionNotFoundError,
)
from app.services.estimation_engine import EstimationMode
from app.services.llm_service import LlmEstimationCallOutcome, UsageInfo
from app.services.sessions import InMemorySessionStore, ProjectMetadata, Session


def _build_app(store: InMemorySessionStore) -> FastAPI:
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")

    settings = Settings(openai_api_key="test-key", llm_domain_guardrail_enabled=False)

    def override_settings() -> Settings:
        return settings

    fake_estimation = MagicMock()
    fake_estimation._providers = []
    service = ConversationalEstimationService(settings, fake_estimation, store)

    app.dependency_overrides[get_settings] = override_settings
    app.dependency_overrides[get_conversational_service] = lambda: service
    return app


def _outcome_for(session: Session, text: str = "## Estimation\n\nDone.") -> SessionEstimateOutcome:
    estimation = LlmEstimationCallOutcome(
        estimation=text,
        provider="openai",
        model="gpt-4o-mini",
        usage=UsageInfo(prompt_tokens=1, completion_tokens=1, total_tokens=2),
        mode=EstimationMode.BASIC,
    )
    return SessionEstimateOutcome(session=session, estimation=estimation)


def test_create_session_returns_distinct_ids() -> None:
    store = InMemorySessionStore()
    client = TestClient(_build_app(store))

    first = client.post("/api/v1/sessions")
    second = client.post("/api/v1/sessions")

    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["session_id"] != second.json()["session_id"]


def test_estimate_in_session_returns_real_estimation_payload() -> None:
    store = InMemorySessionStore()
    session = store.create_session()
    app = _build_app(store)
    service = app.dependency_overrides[get_conversational_service]()

    with patch.object(
        service,
        "run_turn",
        new_callable=AsyncMock,
        return_value=_outcome_for(session),
    ):
        client = TestClient(app)
        response = client.post(
            f"/api/v1/sessions/{session.session_id}/estimate",
            json={"user_message": "Estimate a Python API"},
        )

    assert response.status_code == 200
    assert response.json()["estimation"].startswith("## Estimation")


def test_estimate_unknown_session_returns_404() -> None:
    store = InMemorySessionStore()
    app = _build_app(store)
    service = app.dependency_overrides[get_conversational_service]()
    service.run_turn = AsyncMock(side_effect=SessionNotFoundError("missing"))

    client = TestClient(app)
    response = client.post(
        "/api/v1/sessions/missing/estimate",
        json={"user_message": "hello"},
    )

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_run_turn_invokes_metadata_render_spy() -> None:
    store = InMemorySessionStore()
    session = store.create_session()
    settings = Settings(openai_api_key="test-key", llm_domain_guardrail_enabled=False)
    estimation_service = MagicMock()
    estimation_service._providers = []
    estimation_service._prepare_call = AsyncMock(
        return_value=MagicMock(system_prompt="System base")
    )
    estimation_service.estimate = AsyncMock(
        return_value=LlmEstimationCallOutcome(
            estimation="## Estimation\n\nOK",
            provider="openai",
            model="gpt-4o-mini",
            usage=None,
            mode=EstimationMode.BASIC,
        )
    )
    service = ConversationalEstimationService(settings, estimation_service, store)

    with patch(
        "app.services.conversational_estimation_service.render_session_system_prompt",
        return_value="System with metadata",
    ) as render_mock, patch.object(
        service,
        "_extract_metadata",
        new_callable=AsyncMock,
        return_value=ProjectMetadata(project_name="Portal"),
    ):
        await service.run_turn(session.session_id, "Build portal")

    render_mock.assert_called_once()
