"""HTTP transport envelope for structured estimation (v2 API)."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.estimation_result import EstimationResult
from app.schemas.estimations import AssessmentView, ModeEligibilityView, UsageView
from app.services.estimation_engine import EstimationMode


class EstimationQualityView(BaseModel):
    """Schema-aware diagnostics when ``evaluate`` is true on v2."""

    passed: bool = Field(description="True when the domain model validated successfully.")
    issues: list[str] = Field(default_factory=list)


class EstimationResponse(BaseModel):
    """Typed estimation result plus routing metadata."""

    result: EstimationResult
    prompt_version: str
    examples_version: str
    mode: EstimationMode | None = None
    model: str | None = None
    provider: str | None = None
    request_id: str | None = None
    timestamp: datetime | None = None
    latency_ms: int | None = None
    degraded: bool | None = None
    score: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="1.0 when structured contract satisfied and evaluate=true.",
    )
    usage: UsageView | None = None
    finish_reason: str | None = None
    assessment: AssessmentView | None = None
    mode_eligibility: ModeEligibilityView | None = None
    quality: EstimationQualityView | None = Field(
        default=None,
        description="Present when evaluate=true.",
    )
