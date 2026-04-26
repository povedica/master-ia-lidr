"""Estimation HTTP API."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, field_validator

from app.config import Settings, get_settings
from app.services.llm_service import EstimationError, EstimationService

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


def get_estimation_service(
    settings: Annotated[Settings, Depends(get_settings)],
) -> EstimationService:
    """Provide an estimation service bound to request settings."""

    return EstimationService(settings)


@router.post("/estimate", response_model=EstimateResponse)
async def create_estimate(
    body: EstimateRequest,
    service: Annotated[EstimationService, Depends(get_estimation_service)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> EstimateResponse:
    """Run CAG-style estimation for a single meeting transcription."""

    try:
        estimation = await service.estimate(body.transcription)
    except EstimationError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc

    return EstimateResponse(
        estimation=estimation,
        model=settings.openai_model,
        provider="openai",
    )
