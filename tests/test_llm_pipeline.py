"""Tests for ``LLMPipeline`` orchestration (mocked provider)."""

from __future__ import annotations

import pytest

from app.config import Settings
from app.guardrails.llm_pipeline import LLMPipeline
from app.schemas.estimation_request import EstimationRequest
from app.schemas.estimation_result import EstimationLineItem, EstimationResult, EstimationTotals
from app.services.estimation_engine import EstimationMode, InputAssessment, ModeEligibility
from app.services.estimation_request_render import render_estimation_assessment_surface
from app.services.llm_service import StructuredEstimateBundle, UsageInfo
from tests.estimation_fixtures import minimal_estimation_request_dict


class _StubStructuredService:
    def __init__(self) -> None:
        self.called = False

    async def estimate_structured(
        self,
        request: EstimationRequest,
        *,
        assessment_surface: str,
        skip_domain_guardrail: bool = False,
    ) -> StructuredEstimateBundle:
        self.called = True
        assert skip_domain_guardrail is True
        del request, assessment_surface
        li = EstimationLineItem(name="Task", hours=1.0, cost_eur=10.0)
        totals = EstimationTotals(hours=1.0, cost_eur=10.0)
        result = EstimationResult(
            title="Pipeline unit test",
            summary="Structured summary with enough length for validators.",
            phases=[],
            line_items=[li],
            totals=totals,
            duration_weeks=2.0,
            confidence=0.8,
        )
        assess = InputAssessment(
            detail_level="medium",
            recommended_mode=EstimationMode.STANDARD,
            reason="stub",
        )
        mel = ModeEligibility(
            allowed_modes=(EstimationMode.STANDARD,),
            blocked_modes=(),
            reason=None,
        )
        return StructuredEstimateBundle(
            result=result,
            prompt_version="stub/prompt",
            examples_version="stub/ex",
            mode=EstimationMode.STANDARD,
            model="stub-model",
            provider="stub",
            usage=UsageInfo(prompt_tokens=1, completion_tokens=2, total_tokens=3),
            degraded=False,
            finish_reason="stop",
            assessment=assess,
            mode_eligibility=mel,
        )


@pytest.mark.asyncio
async def test_pipeline_calls_structured_with_skip_domain() -> None:
    settings = Settings(
        openai_api_key="x",
        llm_domain_guardrail_enabled=True,
        guardrail_rollout_prompt_injection_patterns="disabled",
        guardrail_rollout_pii_basic="disabled",
    )
    stub = _StubStructuredService()
    pipeline = LLMPipeline(stub, settings)  # type: ignore[arg-type]
    body = EstimationRequest.model_validate(minimal_estimation_request_dict(evaluate=False))
    assessment_surface = render_estimation_assessment_surface(body)
    outcome = await pipeline.run_structured(
        body,
        assessment_surface=assessment_surface,
        request_id="req_pipeline_test",
    )
    assert stub.called is True
    assert outcome.final_status.value == "success"
    assert outcome.safe_to_cache is True
