"""HTTP transport for grounded RAG estimation."""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator

from app.schemas.estimations import UsageView
from app.schemas.rag_estimation_result import RagEstimationResult


class RagEstimateRequest(BaseModel):
    question: str = Field(..., min_length=1)
    transcript: str | None = Field(
        default=None,
        description="Optional conversation transcript for query reformulation.",
    )
    mode: str | None = Field(default=None, description="Retrieval mode A|B|C|D")
    recall_k: int | None = Field(default=None, ge=1, le=200)
    top_k_final: int | None = Field(default=None, ge=1, le=50)

    @field_validator("question")
    @classmethod
    def strip_question(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("question must not be empty")
        return stripped

    @field_validator("transcript")
    @classmethod
    def strip_transcript(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        if not stripped:
            raise ValueError("transcript must not be empty when provided")
        return stripped


class CitationSummaryView(BaseModel):
    grounded_ok: int
    dangling: int
    insufficient: int
    integrity_violations: int
    has_dangling: bool


class CoherenceSummaryView(BaseModel):
    coherent_ok: int
    total_hours_mismatch: int
    duplicate_component: int
    insufficient_context_violation: int
    zero_hours_grounded: int
    has_violations: bool


class RagEstimationResponse(BaseModel):
    result: RagEstimationResult
    citation_summary: CitationSummaryView
    coherence_summary: CoherenceSummaryView
    request_id: str
    model: str | None = None
    provider: str | None = None
    latency_ms: int | None = None
    usage: UsageView | None = None
