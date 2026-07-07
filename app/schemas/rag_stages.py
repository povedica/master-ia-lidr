"""HTTP schemas for stateless RAG stage endpoints (feature-062)."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from app.schemas.citation_report import CitationReport
from app.schemas.coherence_report import CoherenceReport
from app.schemas.estimation_query import EstimationQuery
from app.schemas.hallucination_report import HallucinationReport
from app.schemas.rag_estimation_result import RagEstimationResult
from app.schemas.rag_structure_result import RagStructureResult
from app.schemas.retrieval_advanced import StageConfigPayload, resolve_request_config
from app.schemas.retrieval_advanced import AdvancedRetrievalRequest


class ReformulateStageRequest(BaseModel):
    question: str = Field(..., min_length=1)
    transcript: str | None = None

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


class ReformulateStageResponse(BaseModel):
    query: EstimationQuery
    search_text: str


class StageChunkView(BaseModel):
    chunk_id: int = Field(..., ge=1)
    document_id: int = Field(..., ge=1)
    content: str = Field(..., min_length=1)
    collection: str = "budgets"
    budget_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class RetrieveStageRequest(BaseModel):
    search_text: str = Field(..., min_length=1)
    mode: Literal["A", "B", "C", "D"] | None = None
    preset: Literal["A", "B", "C", "D"] | None = None
    config: StageConfigPayload | None = None
    recall_k: int | None = Field(default=None, ge=1, le=200)
    top_k_final: int | None = Field(default=None, ge=1, le=50)
    use_advanced: bool = False

    @field_validator("search_text")
    @classmethod
    def strip_search_text(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("search_text must not be empty")
        return stripped

    @model_validator(mode="after")
    def advanced_preset_or_config_exclusive(self) -> RetrieveStageRequest:
        if self.use_advanced and self.preset is not None and self.config is not None:
            raise ValueError("provide either preset or config, not both")
        return self


class RetrieveStageResponse(BaseModel):
    chunks: list[StageChunkView]
    mode: str | None = None
    advanced: bool = False


class AssembleStageRequest(BaseModel):
    chunks: list[StageChunkView] = Field(min_length=1)
    max_context_tokens: int | None = Field(default=None, ge=1)


class AssembleStageResponse(BaseModel):
    context_block: str
    kept_chunks: list[StageChunkView]
    dropped_count: int
    token_count: int


class StructureStageRequest(BaseModel):
    query: EstimationQuery


class StructureStageResponse(BaseModel):
    structure: RagStructureResult


class GenerateStageRequest(BaseModel):
    query: EstimationQuery
    context_block: str = Field(..., min_length=1)
    kept_chunks: list[StageChunkView] = Field(min_length=1)
    question: str | None = Field(
        default=None,
        description="Original user question for prompt rendering; defaults to composed query text.",
    )


class GenerateStageResponse(BaseModel):
    estimate: RagEstimationResult
    fabricated_source_ids: list[int]
    coherent: bool
    citation_report: CitationReport
    coherence_report: CoherenceReport


class VerifyStageRequest(BaseModel):
    estimate: RagEstimationResult
    kept_chunks: list[StageChunkView] = Field(min_length=1)
    use_judge: bool | None = None


class VerifyStageResponse(BaseModel):
    citation_report: CitationReport
    coherence_report: CoherenceReport
    hallucination_report: HallucinationReport


def resolve_retrieve_advanced_config(payload: RetrieveStageRequest):
    if not payload.use_advanced:
        return None
    fake = AdvancedRetrievalRequest(
        query=payload.search_text,
        preset=payload.preset,
        config=payload.config,
        recall_k=payload.recall_k,
        top_k_final=payload.top_k_final,
    )
    return resolve_request_config(fake)
