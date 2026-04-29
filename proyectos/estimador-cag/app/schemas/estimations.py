"""HTTP request/response schemas for estimation endpoints."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from app.services.estimation_engine import EstimationMode


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


class UsageView(BaseModel):
    """Token usage and optional estimated cost metadata."""

    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    estimated_cost_usd: float | None = None


class EstimateResponse(BaseModel):
    """Structured API response including provider metadata."""

    estimation: str
    mode: EstimationMode
    model: str
    provider: str
    request_id: str
    timestamp: datetime
    latency_ms: int
    prompt_version: str
    examples_version: str
    degraded: bool | None = None
    usage: UsageView | None = None

