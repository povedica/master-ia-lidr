"""HTTP transport for grounded RAG estimation."""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator

from app.schemas.estimations import UsageView
from app.schemas.rag_estimation_result import RagEstimationResult


class RagEstimateRequest(BaseModel):
    question: str = Field(..., min_length=1)
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


class CitationSummaryView(BaseModel):
    grounded_ok: int
    dangling: int
    insufficient: int
    integrity_violations: int
    has_dangling: bool


class RagEstimationResponse(BaseModel):
    result: RagEstimationResult
    citation_summary: CitationSummaryView
    request_id: str
    model: str | None = None
    provider: str | None = None
    latency_ms: int | None = None
    usage: UsageView | None = None
