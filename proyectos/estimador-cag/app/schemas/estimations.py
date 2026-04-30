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


class AssessmentView(BaseModel):
    """Input assessment summary returned by the adaptive engine."""

    detail_level: str
    recommended_mode: EstimationMode
    reason: str


class ModeEligibilityView(BaseModel):
    """Business guardrail decision for mode eligibility."""

    allowed_modes: list[EstimationMode]
    blocked_modes: list[EstimationMode]
    reason: str | None = None


class EstimateResponse(BaseModel):
    """Structured API response.

    When DEV_MODE is off, only `estimation` is returned (plus `degraded` when the static
    fallback path was used). Routing metadata, provider identity, timing, versions,
    token usage, and cost appear only when DEV_MODE is true.
    """

    estimation: str
    mode: EstimationMode | None = None
    model: str | None = None
    provider: str | None = None
    request_id: str | None = None
    timestamp: datetime | None = None
    latency_ms: int | None = None
    prompt_version: str | None = None
    examples_version: str | None = None
    assessment: AssessmentView | None = None
    mode_eligibility: ModeEligibilityView | None = None
    degraded: bool | None = None
    usage: UsageView | None = None

