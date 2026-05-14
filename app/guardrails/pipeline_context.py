"""Pipeline execution context and cache-safety metadata."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from app.guardrails.contracts import GuardrailResult
from app.schemas.estimation_request import EstimationRequest


class RenderedPromptRef(BaseModel):
    """Lightweight reference to rendered prompt versions (no raw prompt text)."""

    model_config = ConfigDict(extra="forbid")

    prompt_version: str = Field(..., min_length=1, max_length=128)
    examples_version: str = Field(..., min_length=1, max_length=128)


class CacheMetadata(BaseModel):
    """Cache compatibility metadata (pre-cache guardrails, invalidation hints)."""

    model_config = ConfigDict(extra="forbid")

    looked_up: bool = False
    hit: bool = False
    safe_to_cache: bool = False
    cache_key_fingerprint: str | None = None
    invalidated_because: str | None = Field(
        default=None,
        max_length=256,
        description="Reason metadata changed and a cached entry must not be reused.",
    )


class PipelineContext(BaseModel):
    """Shared mutable-ish state for one guarded estimation run (in-memory only)."""

    model_config = ConfigDict(extra="forbid")

    request_id: str = Field(..., min_length=1, max_length=128)
    audit_id: str = Field(..., min_length=1, max_length=128)
    estimation_request: EstimationRequest | None = None
    user_input: str = Field(default="", max_length=500_000)
    assessment_surface: str = Field(default="", max_length=500_000)
    sanitized_input: str | None = Field(default=None, max_length=500_000)
    prompt_version: str = Field(default="", max_length=128)
    output_schema_version: str = Field(default="1", max_length=32)
    guardrail_rules_version: str = Field(..., min_length=1, max_length=64)
    rendered_prompt: RenderedPromptRef | None = None
    raw_model_output: str | dict[str, object] | None = None
    validation_results: list[GuardrailResult] = Field(default_factory=list)
    timings_ms: dict[str, int] = Field(default_factory=dict)
    provider_metadata: dict[str, str | int | float | bool | None] = Field(default_factory=dict)
    cache_metadata: CacheMetadata | None = None
    retry_count: int = Field(default=0, ge=0, le=64)
    trace_ids: dict[str, str] = Field(default_factory=dict)
