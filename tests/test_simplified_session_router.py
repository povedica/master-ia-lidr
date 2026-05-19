"""Integration tests for simplified session estimate routes."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.config import Settings, get_settings
from app.guardrails.contracts import FinalResponseStatus
from app.guardrails.llm_pipeline import StructuredPipelineOutcome
from app.routers.sessions import get_simplified_session_service, router
from app.schemas.estimation_request import ProjectType, TargetAudience
from app.schemas.estimation_result import EstimationLineItem, EstimationResult, EstimationTotals
from app.schemas.simplified_session import SessionEstimateRequest
from app.services.estimation_engine import EstimationMode, InputAssessment, ModeEligibility
from app.services.llm_service import DomainGuardrailError, StructuredEstimateBundle, UsageInfo
from app.services.simplified_session_estimation_service import (
    SessionNotFoundError,
    SimplifiedSessionSubmitOutcome,
)
from app.services.sessions import DerivedProjectMetadata, InMemorySessionStore, Session


def _build_app(store: InMemorySessionStore) -> FastAPI:
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    settings = Settings(openai_api_key="test-key", llm_domain_guardrail_enabled=False)
    fake_service = MagicMock()

    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_simplified_session_service] = lambda: fake_service
    app.state._test_service = fake_service  # type: ignore[attr-defined]
    app.state._test_store = store  # type: ignore[attr-defined]
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


def _submit_outcome(session: Session) -> SimplifiedSessionSubmitOutcome:
    metadata = DerivedProjectMetadata(
        project_name="Portal",
        project_type=ProjectType.web_saas,
        target_audience=TargetAudience.b2b_smb,
        summary="Summary text",
    )
    return SimplifiedSessionSubmitOutcome(
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
        warnings=["industry was not provided"],
        normalized_payload={"project_name": "Portal"},
        derived_metadata=metadata,
        attachment_statuses=[],
    )


def test_estimate_returns_envelope_with_project_metadata() -> None:
    store = InMemorySessionStore()
    session = store.create_session()
    app = _build_app(store)
    service = app.state._test_service
    service.run_submit = AsyncMock(return_value=_submit_outcome(session))

    with patch("app.routers.sessions.session_store", store):
        client = TestClient(app)
        response = client.post(
            f"/api/v1/sessions/{session.session_id}/estimate",
            json=SessionEstimateRequest(
                project_name="Portal",
                project_type=ProjectType.web_saas,
                transcript="A" * 80,
                target_audience=TargetAudience.b2b_smb,
            ).model_dump(mode="json"),
        )

    assert response.status_code == 200
    body = response.json()
    assert body["session_id"] == session.session_id
    assert body["project_metadata"]["project_name"] == "Portal"
    assert body["warnings"]
    assert body["estimate"]["result"]["title"] == "Estimate"


def test_estimate_unknown_session_returns_404() -> None:
    store = InMemorySessionStore()
    app = _build_app(store)
    service = app.state._test_service
    service.run_submit = AsyncMock(side_effect=SessionNotFoundError("missing"))

    with patch("app.routers.sessions.session_store", store):
        client = TestClient(app)
        response = client.post(
            "/api/v1/sessions/missing/estimate",
            json=SessionEstimateRequest(
                project_name="Portal",
                project_type=ProjectType.web_saas,
                transcript="A" * 80,
                target_audience=TargetAudience.b2b_smb,
            ).model_dump(mode="json"),
        )

    assert response.status_code == 404


def test_estimate_returns_422_for_domain_guardrail() -> None:
    store = InMemorySessionStore()
    session = store.create_session()
    app = _build_app(store)
    service = app.state._test_service
    service.run_submit = AsyncMock(
        side_effect=DomainGuardrailError("Only software/project estimation requests are supported."),
    )

    with patch("app.routers.sessions.session_store", store):
        client = TestClient(app)
        response = client.post(
            f"/api/v1/sessions/{session.session_id}/estimate",
            json=SessionEstimateRequest(
                project_name="Portal",
                project_type=ProjectType.web_saas,
                transcript="A" * 80,
                target_audience=TargetAudience.b2b_smb,
            ).model_dump(mode="json"),
        )

    assert response.status_code == 422
    body = response.json()
    assert body["detail"]["code"] == "out_of_domain"


def test_estimate_rejects_legacy_user_message_body() -> None:
    store = InMemorySessionStore()
    session = store.create_session()
    with patch("app.routers.sessions.session_store", store):
        client = TestClient(_build_app(store))
        response = client.post(
            f"/api/v1/sessions/{session.session_id}/estimate",
            json={"user_message": "hello"},
        )

    assert response.status_code == 422
