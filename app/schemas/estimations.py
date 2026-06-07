"""HTTP request/response schemas for estimation endpoints."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class StructureCheckView(BaseModel):
    """Full Level-1 structural evaluation from ``evaluate_estimation_structure``.

    Present in the response when the client sends ``evaluate: true`` (default).
    The ``score`` field matches ``EstimateResponse.score`` for the same request.
    """

    has_title: bool
    has_breakdown_table: bool
    has_totals_section: bool
    has_team_section: bool
    has_duration_section: bool
    declared_total_hours: int | None = None
    sum_row_hours: int | None = None
    hours_match: bool | None = None
    declared_total_cost: int | None = None
    sum_row_cost: int | None = None
    cost_match: bool | None = None
    finish_reason_ok: bool
    score: float = Field(..., ge=0.0, le=1.0)
    issues: list[str]


class UsageView(BaseModel):
    """Token usage and optional estimated cost metadata."""

    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    preprocessing_input_tokens: int = 0
    preprocessing_output_tokens: int = 0
    estimated_cost_usd: float | None = None


class EstimateResponse(BaseModel):
    """Structured API response.

    When ``evaluate`` is true on the request (default, same as ai-engineering/estimator),
    ``score`` and ``structure_evaluation`` mirror ``EstimationResponse.validation`` from the
    reference repo: ``evaluate_estimation_structure().score`` (mean of boolean gates, 3 decimals).
    When ``evaluate`` is false, those fields are omitted. Full routing metadata appears only when
    DEV_MODE is true.
    """

    estimation: str
    score: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Level-1 structural score; present when the client set evaluate=true.",
    )
    model: str | None = None
    provider: str | None = None
    request_id: str | None = None
    timestamp: datetime | None = None
    latency_ms: int | None = None
    prompt_version: str | None = None
    examples_version: str | None = None
    degraded: bool | None = None
    usage: UsageView | None = None
    finish_reason: str | None = Field(
        default=None,
        description="Provider stop reason when DEV_MODE is true (e.g. OpenAI finish_reason, Anthropic stop_reason).",
    )
    structure_evaluation: StructureCheckView | None = Field(
        default=None,
        description="Full Level-1 structural score breakdown (evaluate_estimation_structure). Present when evaluate=true.",
    )
