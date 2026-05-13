"""Assemble ``EstimationResponse`` for the v2 structured API."""

from __future__ import annotations

from datetime import datetime

from app.schemas.estimation_response import EstimationQualityView, EstimationResponse
from app.schemas.estimations import AssessmentView, ModeEligibilityView, UsageView
from app.services.estimate_response_builder import estimate_cost_usd
from app.services.llm_service import StructuredEstimateBundle


def assemble_estimation_v2_response(
    bundle: StructuredEstimateBundle,
    *,
    evaluate: bool,
    dev_mode: bool,
    request_id: str,
    finished_at: datetime,
    latency_ms: int,
) -> EstimationResponse:
    """Build the HTTP envelope from a structured estimation bundle."""

    quality: EstimationQualityView | None = None
    score: float | None = None
    if evaluate:
        quality = EstimationQualityView(passed=True, issues=[])
        score = 1.0

    if not dev_mode:
        return EstimationResponse(
            result=bundle.result,
            prompt_version=bundle.prompt_version,
            examples_version=bundle.examples_version,
            mode=bundle.mode,
            score=score,
            quality=quality,
        )

    usage_view: UsageView | None = None
    if bundle.usage is not None:
        usage_view = UsageView(
            prompt_tokens=bundle.usage.prompt_tokens,
            completion_tokens=bundle.usage.completion_tokens,
            total_tokens=bundle.usage.total_tokens,
            preprocessing_input_tokens=bundle.usage.preprocessing_input_tokens,
            preprocessing_output_tokens=bundle.usage.preprocessing_output_tokens,
        )
        usage_view.estimated_cost_usd = estimate_cost_usd(bundle.model, usage_view)

    return EstimationResponse(
        result=bundle.result,
        prompt_version=bundle.prompt_version,
        examples_version=bundle.examples_version,
        mode=bundle.mode,
        model=bundle.model,
        provider=bundle.provider,
        request_id=request_id,
        timestamp=finished_at,
        latency_ms=latency_ms,
        degraded=bundle.degraded,
        score=score,
        usage=usage_view,
        finish_reason=bundle.finish_reason,
        assessment=AssessmentView(
            detail_level=bundle.assessment.detail_level,
            recommended_mode=bundle.assessment.recommended_mode,
            reason=bundle.assessment.reason,
        ),
        mode_eligibility=ModeEligibilityView(
            allowed_modes=list(bundle.mode_eligibility.allowed_modes),
            blocked_modes=list(bundle.mode_eligibility.blocked_modes),
            reason=bundle.mode_eligibility.reason,
        ),
        quality=quality,
    )
