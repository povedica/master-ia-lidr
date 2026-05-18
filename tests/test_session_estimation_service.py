"""Unit tests for ``SessionEstimationService``."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.config import Settings
from app.guardrails.contracts import FinalResponseStatus
from app.guardrails.llm_pipeline import StructuredPipelineOutcome
from app.schemas.estimation_result import EstimationLineItem, EstimationResult, EstimationTotals
from app.services.estimation_engine import EstimationMode, InputAssessment, ModeEligibility
from app.services.llm_service import StructuredEstimateBundle
from app.services.session_estimation_service import SessionEstimationService, SessionNotFoundError
from app.services.sessions import InMemorySessionStore
from tests.estimation_fixtures import minimal_estimation_request_dict

from app.schemas.estimation_request import EstimationRequest


def _structured_bundle() -> StructuredEstimateBundle:
    li = EstimationLineItem(name="Task", hours=2.0, cost_eur=100.0)
    totals = EstimationTotals(hours=2.0, cost_eur=100.0)
    result = EstimationResult(
        title="Portal estimate",
        summary="S" * 25,
        phases=[],
        line_items=[li],
        totals=totals,
        duration_weeks=1.0,
        confidence=0.7,
    )
    return StructuredEstimateBundle(
        result=result,
        prompt_version="estimation/v2",
        examples_version="fixture",
        mode=EstimationMode.STANDARD,
        model="gpt-4o-mini",
        provider="openai",
        usage=None,
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


@pytest.mark.asyncio
async def test_run_submit_updates_session_memory() -> None:
    store = InMemorySessionStore()
    session = store.create_session()
    settings = Settings(openai_api_key="test-key", llm_domain_guardrail_enabled=False)
    estimation_service = MagicMock()
    estimation_service._providers = []
    estimation_service.prepare_structured_prelude = AsyncMock(
        return_value=MagicMock(
            mode=EstimationMode.STANDARD,
            preprocessed_markdown_for_template=None,
        )
    )
    service = SessionEstimationService(settings, estimation_service, store)
    request = EstimationRequest(**minimal_estimation_request_dict(project_name="Portal"))

    pipeline_outcome = StructuredPipelineOutcome(
        bundle=_structured_bundle(),
        final_status=FinalResponseStatus.SUCCESS,
        reason_code=None,
        user_message=None,
        technical_message=None,
        audit_id="audit-1",
        safe_to_cache=True,
        safe_to_display=True,
    )

    with patch("app.services.session_estimation_service.LLMPipeline") as pipeline_cls:
        pipeline_cls.return_value.run_structured = AsyncMock(return_value=pipeline_outcome)
        outcome = await service.run_submit(session.session_id, request, request_id="req-1")

    assert outcome.session.submit_count == 1
    assert outcome.session.last_estimation_request is not None
    assert outcome.session.last_estimation_request.project_name == "Portal"
    messages = outcome.session.conversation_history.to_messages_list()
    assert any(m["role"] == "user" and "[Form submit]" in m["content"] for m in messages)
    assert any(m["role"] == "assistant" for m in messages)


@pytest.mark.asyncio
async def test_run_submit_unknown_session_raises() -> None:
    store = InMemorySessionStore()
    settings = Settings(openai_api_key="test-key")
    service = SessionEstimationService(settings, MagicMock(), store)
    request = EstimationRequest(**minimal_estimation_request_dict())

    with pytest.raises(SessionNotFoundError):
        await service.run_submit("missing", request, request_id="req-1")
