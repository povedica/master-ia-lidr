"""Typed contracts for guardrail checks, policy execution, and pipeline metadata."""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class GuardrailLayer(StrEnum):
    """Validation quadrant / pipeline layer for a guardrail."""

    INPUT_SYNTACTIC = "input_syntactic"
    INPUT_SEMANTIC = "input_semantic"
    OUTPUT_SYNTACTIC = "output_syntactic"
    OUTPUT_SEMANTIC = "output_semantic"


class GuardrailSeverity(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class GuardrailPolicy(StrEnum):
    """Explicit on-failure policy for a guardrail (no implicit defaults)."""

    EXCEPTION = "exception"
    FIX_RETRY = "fix_retry"
    FILTER = "filter"


class RolloutMode(StrEnum):
    DISABLED = "disabled"
    LOG_ONLY = "log_only"
    ENFORCE = "enforce"


class PolicyOutcomeStatus(StrEnum):
    """What happened when a policy was evaluated for a guardrail result."""

    NONE = "none"
    ENFORCED = "enforced"
    RECORDED_LOG_ONLY = "recorded_log_only"


class GuardrailResult(BaseModel):
    """Normalized result for any guardrail check."""

    model_config = ConfigDict(extra="forbid")

    guardrail_id: str = Field(..., min_length=1, max_length=128)
    layer: GuardrailLayer
    passed: bool
    reasons: list[str] = Field(default_factory=list)
    severity: GuardrailSeverity
    matched_rules: list[str] = Field(default_factory=list)
    moderation_scores: dict[str, float] = Field(default_factory=dict)
    recommended_policy: GuardrailPolicy
    audit_payload: dict[str, str | int | float | bool | None] = Field(default_factory=dict)


class ConfidenceAssessment(BaseModel):
    """Optional structured confidence signal for output semantic checks."""

    model_config = ConfigDict(extra="forbid")

    score: float = Field(..., ge=0.0, le=1.0)
    label: str = Field(..., min_length=1, max_length=64)


class OutputSemanticGuardrailResult(GuardrailResult):
    """Output semantic layer: extends base with presentation-safety flags."""

    confidence_assessment: ConfidenceAssessment | None = None
    redaction_applied: bool = False
    safe_fallback_needed: bool = False


class PolicyOutcome(BaseModel):
    """Structured outcome after applying a failure policy to a guardrail result."""

    model_config = ConfigDict(extra="forbid")

    guardrail_id: str = Field(..., min_length=1, max_length=128)
    policy: GuardrailPolicy
    status: PolicyOutcomeStatus
    reason_code: str = Field(..., min_length=1, max_length=128)
    retry_allowed: bool = False
    retry_after_fix: bool = False
    fallback_response: Any = Field(
        default=None,
        description="Populated with FinalEstimationResponse when that transport model exists.",
    )
    audit_payload: dict[str, str | int | float | bool | None] = Field(default_factory=dict)


class GuardrailDeclaration(BaseModel):
    """Central registry row: single source of truth for guardrail metadata."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(..., min_length=1, max_length=128)
    description: str = Field(..., min_length=1, max_length=512)
    layer: GuardrailLayer
    severity: GuardrailSeverity
    on_fail: GuardrailPolicy
    retry_max: int = Field(default=0, ge=0, le=32)
    rollout: RolloutMode
    thresholds: dict[str, float] = Field(default_factory=dict)
    rules_version: str = Field(..., min_length=1, max_length=64)
    metrics_event_name: str | None = Field(default=None, max_length=128)
    cache_safe_when_passed: bool = Field(
        default=True,
        description="When False, a passing check still blocks caching (rare).",
    )
