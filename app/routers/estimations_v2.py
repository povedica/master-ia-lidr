"""Structured estimation API (v2): Jinja prompts + Pydantic-first responses."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from time import perf_counter
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.config import Settings, get_settings
from app.guardrails.exceptions import GuardrailViolationError
from app.guardrails.llm_pipeline import LLMPipeline
from app.schemas.estimation_request import EstimationRequest
from app.schemas.estimation_response import EstimationResponse
from app.schemas.estimations import UsageView
from app.services.estimation_request_render import render_estimation_assessment_surface
from app.services.estimation_stats_logger import (
    resolve_stats_log_path,
    try_append_estimation_stats,
)
from app.services.estimation_v2_response_builder import assemble_estimation_v2_response
from app.services.estimate_response_builder import estimate_cost_usd
from app.services.llm_call_audit import merge_llm_call_audit
from app.services.llm_chain import build_provider_chain
from app.services.llm_service import (
    EXAMPLES_VERSION,
    PROMPT_VERSION,
    EstimationService,
    LlmEstimationCallOutcome,
)
from app.services.observability.bootstrap import get_observability
from app.services.observability.session import resolve_session_id
from app.services.observability.types import TelemetryContext
from app.services.response_output_writer import (
    ResponseOutputPersistError,
    persist_estimation_json,
)

router = APIRouter(tags=["estimations-v2"])
logger = logging.getLogger(__name__)

V2_ESTIMATE_TRACE_NAME = "estimator.api.v2.estimate"


def get_estimation_service(
    settings: Annotated[Settings, Depends(get_settings)],
) -> EstimationService:
    return EstimationService(settings, build_provider_chain(settings))


@router.post(
    "/estimate",
    response_model=EstimationResponse,
    response_model_exclude_none=True,
)
async def create_estimate_structured(
    body: EstimationRequest,
    request: Request,
    service: Annotated[EstimationService, Depends(get_estimation_service)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> EstimationResponse:
    """Return a validated structured ``EstimationResult`` (no Markdown primary payload)."""

    start = perf_counter()
    request_id = f"est_{uuid4().hex[:12]}"
    session_id = resolve_session_id(request)
    observability = get_observability()
    observability.set_prompt_context(
        prompt_version=PROMPT_VERSION,
        examples_version=EXAMPLES_VERSION,
    )
    trace_context = TelemetryContext(
        request_id=request_id,
        feature="estimation",
        session_id=session_id,
        tags=["feature:estimation", "endpoint:api_v2_estimate"],
        metadata={
            "prompt_version": PROMPT_VERSION,
            "examples_version": EXAMPLES_VERSION,
        },
    )

    with observability.start_trace(V2_ESTIMATE_TRACE_NAME, context=trace_context):
        try:
            return await _execute_v2_estimate(
                body=body,
                service=service,
                settings=settings,
                request_id=request_id,
                started_at_perf=start,
            )
        except HTTPException as exc:
            observability.set_http_status(exc.status_code)
            raise


async def _execute_v2_estimate(
    *,
    body: EstimationRequest,
    service: EstimationService,
    settings: Settings,
    request_id: str,
    started_at_perf: float,
) -> EstimationResponse:
    assessment_surface = render_estimation_assessment_surface(body)
    pipeline = LLMPipeline(service, settings)
    observability = get_observability()

    merge_llm_call_audit(request_id=request_id)

    with observability.start_span("estimator.pipeline.structured"):
        try:
            outcome = await pipeline.run_structured(
                body,
                assessment_surface=assessment_surface,
                request_id=request_id,
            )
        except GuardrailViolationError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail={
                    "code": exc.reason_code,
                    "message": exc.user_message,
                    "audit_id": exc.audit_id,
                },
            ) from exc

    if outcome.bundle is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": outcome.reason_code or "error",
                "message": outcome.user_message or "Unable to complete structured estimation.",
                "audit_id": outcome.audit_id,
            },
        )

    bundle = outcome.bundle
    if settings.estimation_output_persist_enabled:
        try:
            destination = persist_estimation_json(bundle.result.model_dump_json(indent=2))
            logger.info("estimation_output_persisted", extra={"path": str(destination)})
        except ResponseOutputPersistError as exc:
            logger.warning("estimation_output_persist_failed")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Unable to persist estimation output.",
            ) from exc

    finished_at = datetime.now(UTC)
    latency_ms = int((perf_counter() - started_at_perf) * 1000)

    response = assemble_estimation_v2_response(
        bundle,
        evaluate=body.evaluate,
        dev_mode=settings.dev_mode,
        request_id=request_id,
        finished_at=finished_at,
        latency_ms=latency_ms,
        pipeline_final_status=outcome.final_status,
        pipeline_reason_code=outcome.reason_code,
        pipeline_user_message=outcome.user_message,
        pipeline_technical_message=outcome.technical_message,
        pipeline_audit_id=outcome.audit_id,
        pipeline_safe_to_cache=outcome.safe_to_cache,
        pipeline_safe_to_display=outcome.safe_to_display,
        pipeline_cached=outcome.cached,
        pipeline_cache_score=outcome.cache_score,
        pipeline_cache_bucket=outcome.cache_bucket,
        pipeline_cache_miss_reason=outcome.cache_miss_reason,
    )

    if settings.estimation_stats_log_enabled:
        cost: float | None = None
        if bundle.usage:
            usage_for_cost = UsageView(
                prompt_tokens=bundle.usage.prompt_tokens,
                completion_tokens=bundle.usage.completion_tokens,
                total_tokens=bundle.usage.total_tokens,
                preprocessing_input_tokens=bundle.usage.preprocessing_input_tokens,
                preprocessing_output_tokens=bundle.usage.preprocessing_output_tokens,
            )
            cost = estimate_cost_usd(bundle.model, usage_for_cost)
        stats_outcome = LlmEstimationCallOutcome(
            estimation="",
            provider=bundle.provider,
            model=bundle.model,
            usage=bundle.usage,
            degraded=bundle.degraded,
            finish_reason=bundle.finish_reason,
        )
        try_append_estimation_stats(
            path=resolve_stats_log_path(settings.estimation_stats_log_path),
            result=stats_outcome,
            structure_score=response.score if response.score is not None else 0.0,
            request_id=request_id,
            timestamp=finished_at,
            latency_ms=latency_ms,
            prompt_version=bundle.prompt_version,
            examples_version=bundle.examples_version,
            estimated_cost_usd=cost,
        )

    observability.set_http_status(status.HTTP_200_OK)
    return response
