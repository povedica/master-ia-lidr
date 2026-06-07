"""Assemble ``EstimationResponse`` for the v2 structured API."""

from __future__ import annotations

from datetime import datetime

from app.guardrails.contracts import FinalResponseStatus
from app.schemas.acb.trace import AcbTrace
from app.schemas.estimation_response import EstimationQualityView, EstimationResponse
from app.schemas.estimations import UsageView
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
    pipeline_final_status: FinalResponseStatus | None = None,
    pipeline_reason_code: str | None = None,
    pipeline_user_message: str | None = None,
    pipeline_technical_message: str | None = None,
    pipeline_audit_id: str | None = None,
    pipeline_safe_to_cache: bool | None = None,
    pipeline_safe_to_display: bool | None = None,
    pipeline_cached: bool = False,
    pipeline_cache_score: float | None = None,
    pipeline_cache_bucket: str | None = None,
    pipeline_cache_miss_reason: str | None = None,
    acb_trace: AcbTrace | None = None,
) -> EstimationResponse:
    """Build the HTTP envelope from a structured estimation bundle."""

    quality: EstimationQualityView | None = None
    score: float | None = None
    if evaluate:
        if pipeline_final_status == FinalResponseStatus.DEGRADED:
            quality = EstimationQualityView(
                passed=False,
                issues=[pipeline_reason_code or "degraded"],
            )
            score = 0.0
        else:
            quality = EstimationQualityView(passed=True, issues=[])
            score = 1.0

    pipeline_kwargs = dict(
        final_status=pipeline_final_status,
        reason_code=pipeline_reason_code,
        user_message=pipeline_user_message,
        technical_message=pipeline_technical_message,
        audit_id=pipeline_audit_id,
        safe_to_cache=pipeline_safe_to_cache,
        safe_to_display=pipeline_safe_to_display,
        cached=pipeline_cached,
        cache_score=pipeline_cache_score,
        cache_bucket=pipeline_cache_bucket,
        cache_miss_reason=pipeline_cache_miss_reason,
    )

    if not dev_mode:
        return EstimationResponse(
            result=bundle.result,
            prompt_version=bundle.prompt_version,
            examples_version=bundle.examples_version,
            score=score,
            quality=quality,
            **pipeline_kwargs,
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
        model=bundle.model,
        provider=bundle.provider,
        request_id=request_id,
        timestamp=finished_at,
        latency_ms=latency_ms,
        degraded=bundle.degraded,
        score=score,
        usage=usage_view,
        finish_reason=bundle.finish_reason,
        quality=quality,
        acb_trace=acb_trace,
        **pipeline_kwargs,
    )
