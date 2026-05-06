"""Estimation HTTP API."""

import logging
from datetime import UTC, datetime
from time import perf_counter
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status

from app.config import Settings, get_settings
from app.schemas.estimations import EstimateRequest, EstimateResponse, UsageView
from app.services.estimate_response_builder import assemble_estimate_response, estimate_cost_usd
from app.services.providers import build_provider_chain
from app.services.llm_service import DomainGuardrailError, EXAMPLES_VERSION, PROMPT_VERSION, EstimationError, EstimationService
from app.services.estimation_stats_logger import (
    resolve_stats_log_path,
    try_append_estimation_stats,
)
from app.services.response_output_writer import (
    ResponseOutputPersistError,
    persist_estimation_output,
)

router = APIRouter(tags=["estimations"])
logger = logging.getLogger(__name__)


def get_estimation_service(
    settings: Annotated[Settings, Depends(get_settings)],
) -> EstimationService:
    """Provide an estimation service bound to request settings."""

    return EstimationService(settings, build_provider_chain(settings))


@router.post(
    "/estimate",
    response_model=EstimateResponse,
    response_model_exclude_none=True,
)
async def create_estimate(
    body: EstimateRequest,
    service: Annotated[EstimationService, Depends(get_estimation_service)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> EstimateResponse:
    """Run CAG-style estimation for a single meeting transcription."""

    start = perf_counter()
    request_id = f"est_{uuid4().hex[:12]}"
    try:
        result = await service.estimate(body.transcription, preprocessing=body.preprocessing)
    except DomainGuardrailError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={
                "code": exc.code,
                "message": str(exc),
            },
        ) from exc
    except EstimationError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc

    if settings.estimation_output_persist_enabled:
        try:
            destination = persist_estimation_output(result.estimation)
            logger.info(
                "estimation_output_persisted",
                extra={"path": str(destination)},
            )
        except ResponseOutputPersistError as exc:
            logger.warning("estimation_output_persist_failed")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Unable to persist estimation output.",
            ) from exc

    finished_at = datetime.now(UTC)
    latency_ms = int((perf_counter() - start) * 1000)

    response, structure_check = assemble_estimate_response(
        result,
        evaluate=body.evaluate,
        dev_mode=settings.dev_mode,
        stats_log_enabled=settings.estimation_stats_log_enabled,
        request_id=request_id,
        finished_at=finished_at,
        latency_ms=latency_ms,
    )

    if settings.estimation_stats_log_enabled:
        cost: float | None = None
        if result.usage:
            usage_for_cost = UsageView(
                prompt_tokens=result.usage.prompt_tokens,
                completion_tokens=result.usage.completion_tokens,
                total_tokens=result.usage.total_tokens,
                preprocessing_input_tokens=result.usage.preprocessing_input_tokens,
                preprocessing_output_tokens=result.usage.preprocessing_output_tokens,
            )
            cost = estimate_cost_usd(result.model, usage_for_cost)
        if structure_check is None:
            logger.warning(
                "estimation_stats_skipped_no_structure_check",
                extra={"request_id": request_id},
            )
        else:
            try_append_estimation_stats(
                path=resolve_stats_log_path(settings.estimation_stats_log_path),
                result=result,
                structure_score=structure_check.score,
                request_id=request_id,
                timestamp=finished_at,
                latency_ms=latency_ms,
                prompt_version=PROMPT_VERSION,
                examples_version=EXAMPLES_VERSION,
                estimated_cost_usd=cost,
            )

    return response
