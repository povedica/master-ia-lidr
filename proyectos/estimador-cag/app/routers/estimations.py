"""Estimation HTTP API."""

import logging
from datetime import UTC, datetime
from time import perf_counter
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status

from app.config import Settings, get_settings
from app.schemas.estimations import (
    AssessmentView,
    EstimateRequest,
    EstimateResponse,
    ModeEligibilityView,
    StructureCheckView,
    UsageView,
)
from app.services.evaluation import evaluate_estimation_structure
from app.services.estimation_output_validation import evaluate_estimation_output
from app.services.providers import build_provider_chain
from app.services.llm_service import (
    DomainGuardrailError,
    EXAMPLES_VERSION,
    PROMPT_VERSION,
    EstimationError,
    EstimationService,
)
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


_MODEL_COSTS_PER_1M_TOKENS: dict[str, tuple[float, float]] = {
    "gpt-4o-mini": (0.15, 0.60),
}


def _estimate_cost_usd(model: str, usage: UsageView | None) -> float | None:
    """Estimate request cost in USD when token pricing is known."""

    if usage is None:
        return None
    prices = _MODEL_COSTS_PER_1M_TOKENS.get(model)
    if prices is None:
        return None
    input_price, output_price = prices
    cost = (
        (usage.prompt_tokens / 1_000_000) * input_price
        + (usage.completion_tokens / 1_000_000) * output_price
    )
    return round(cost, 8)


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
    degraded_value = True if result.degraded else None

    output_validation = None
    structure_evaluation = None
    structure_check = None
    if body.evaluate or settings.estimation_stats_log_enabled:
        finish = (result.finish_reason or "").strip() or "stop"
        structure_check = evaluate_estimation_structure(result.estimation, finish)
    if body.evaluate and structure_check is not None:
        output_validation = evaluate_estimation_output(
            result.estimation,
            result.mode,
            result.finish_reason,
        )
        structure_evaluation = StructureCheckView(
            has_title=structure_check.has_title,
            has_breakdown_table=structure_check.has_breakdown_table,
            has_totals_section=structure_check.has_totals_section,
            has_team_section=structure_check.has_team_section,
            has_duration_section=structure_check.has_duration_section,
            declared_total_hours=structure_check.declared_total_hours,
            sum_row_hours=structure_check.sum_row_hours,
            hours_match=structure_check.hours_match,
            declared_total_cost=structure_check.declared_total_cost,
            sum_row_cost=structure_check.sum_row_cost,
            cost_match=structure_check.cost_match,
            finish_reason_ok=structure_check.finish_reason_ok,
            score=structure_check.score,
            issues=structure_check.issues,
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
            cost = _estimate_cost_usd(result.model, usage_for_cost)
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

    response_score = structure_check.score if body.evaluate and structure_check else None

    if not settings.dev_mode:
        return EstimateResponse(
            estimation=result.estimation,
            score=response_score,
            degraded=degraded_value,
            output_validation=output_validation,
            structure_evaluation=structure_evaluation,
        )

    usage: UsageView | None = None
    if result.usage:
        usage = UsageView(
            prompt_tokens=result.usage.prompt_tokens,
            completion_tokens=result.usage.completion_tokens,
            total_tokens=result.usage.total_tokens,
            preprocessing_input_tokens=result.usage.preprocessing_input_tokens,
            preprocessing_output_tokens=result.usage.preprocessing_output_tokens,
        )
        usage.estimated_cost_usd = _estimate_cost_usd(result.model, usage)

    return EstimateResponse(
        estimation=result.estimation,
        score=response_score,
        mode=result.mode,
        model=result.model,
        provider=result.provider,
        request_id=request_id,
        timestamp=finished_at,
        latency_ms=latency_ms,
        prompt_version=PROMPT_VERSION,
        examples_version=EXAMPLES_VERSION,
        assessment=(
            AssessmentView(
                detail_level=result.assessment.detail_level,
                recommended_mode=result.assessment.recommended_mode,
                reason=result.assessment.reason,
            )
            if result.assessment
            else None
        ),
        mode_eligibility=(
            ModeEligibilityView(
                allowed_modes=list(result.mode_eligibility.allowed_modes),
                blocked_modes=list(result.mode_eligibility.blocked_modes),
                reason=result.mode_eligibility.reason,
            )
            if result.mode_eligibility
            else None
        ),
        degraded=degraded_value,
        usage=usage,
        finish_reason=result.finish_reason,
        output_validation=output_validation,
        structure_evaluation=structure_evaluation,
    )
