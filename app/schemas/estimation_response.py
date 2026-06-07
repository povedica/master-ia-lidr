"""HTTP transport envelope for structured estimation (v2 API)."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from app.guardrails.contracts import FinalResponseStatus
from app.schemas.estimation_result import EstimationResult
from app.schemas.estimations import UsageView


class EstimationQualityView(BaseModel):
    """Schema-aware diagnostics when ``evaluate`` is true on v2."""

    passed: bool = Field(description="True when the domain model validated successfully.")
    issues: list[str] = Field(default_factory=list)


class EstimationResponse(BaseModel):
    """Typed estimation result plus metadata."""

    result: EstimationResult
    prompt_version: str
    examples_version: str
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
    quality: EstimationQualityView | None = Field(
        default=None,
        description="Present when evaluate=true.",
    )
    final_status: FinalResponseStatus | None = Field(
        default=None,
        description="Guarded pipeline status; omitted on legacy responses.",
    )
    reason_code: str | None = Field(
        default=None,
        max_length=128,
        description="Stable machine-readable reason when final_status is set.",
    )
    user_message: str | None = Field(
        default=None,
        max_length=2000,
        description="Safe user-facing explanation when the pipeline degrades or rejects.",
    )
    technical_message: str | None = Field(
        default=None,
        max_length=2000,
        description="Optional diagnostic text; not intended for direct UI display.",
    )
    audit_id: str | None = Field(default=None, max_length=128)
    safe_to_cache: bool | None = Field(
        default=None,
        description="Whether a cached representation would be considered safe.",
    )
    safe_to_display: bool | None = Field(
        default=None,
        description="Whether the structured result is safe to render without redaction.",
    )
    cached: bool = Field(default=False, description="True when the response was served from semantic cache.")
    cache_score: float | None = Field(
        default=None,
        description="Top cosine similarity when semantic cache ran; null on full miss paths.",
    )
    cache_bucket: str | None = Field(
        default=None,
        max_length=256,
        description="Opaque semantic cache bucket label (no raw user text).",
    )
    cache_miss_reason: str | None = Field(
        default=None,
        max_length=64,
        description="Stable miss reason when semantic cache did not serve a hit.",
    )
