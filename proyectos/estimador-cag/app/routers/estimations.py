"""Estimation HTTP API."""

from datetime import UTC, datetime
from time import perf_counter
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, field_validator

from app.config import Settings, get_settings
from app.services.llm_service import (
    EXAMPLES_VERSION,
    PROMPT_VERSION,
    EstimationError,
    EstimationService,
)

router = APIRouter(tags=["estimations"])


class EstimateRequest(BaseModel):
    """Inbound meeting transcription to estimate."""

    transcription: str = Field(..., min_length=1)

    @field_validator("transcription")
    @classmethod
    def strip_transcription(cls, value: str) -> str:
        """Reject blank strings after trimming whitespace."""

        stripped = value.strip()
        if not stripped:
            raise ValueError("transcription must not be empty")
        return stripped


class EstimateResponse(BaseModel):
    """Structured API response including provider metadata."""

    estimation: str
    model: str
    provider: str
    request_id: str
    timestamp: datetime
    latency_ms: int
    prompt_version: str
    examples_version: str
    usage: dict[str, int | float] | None = None


_MODEL_COSTS_PER_1M_TOKENS: dict[str, tuple[float, float]] = {
    "gpt-4o-mini": (0.15, 0.60),
}


def _estimate_cost_usd(model: str, usage: dict[str, int] | None) -> float | None:
    """Estimate request cost in USD when token pricing is known."""

    if usage is None:
        return None
    prices = _MODEL_COSTS_PER_1M_TOKENS.get(model)
    if prices is None:
        return None
    input_price, output_price = prices
    cost = (
        (usage["prompt_tokens"] / 1_000_000) * input_price
        + (usage["completion_tokens"] / 1_000_000) * output_price
    )
    return round(cost, 8)


def get_estimation_service(
    settings: Annotated[Settings, Depends(get_settings)],
) -> EstimationService:
    """Provide an estimation service bound to request settings."""

    return EstimationService(settings)


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
        result = await service.estimate(body.transcription)
    except EstimationError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc

    usage = None
    if settings.dev_mode and result.usage:
        usage = {
            "prompt_tokens": result.usage.prompt_tokens,
            "completion_tokens": result.usage.completion_tokens,
            "total_tokens": result.usage.total_tokens,
        }
        usage["estimated_cost_usd"] = _estimate_cost_usd(settings.openai_model, usage)

    return EstimateResponse(
        estimation=result.estimation,
        model=settings.openai_model,
        provider="openai",
        request_id=request_id,
        timestamp=datetime.now(UTC),
        latency_ms=int((perf_counter() - start) * 1000),
        prompt_version=PROMPT_VERSION,
        examples_version=EXAMPLES_VERSION,
        usage=usage,
    )
