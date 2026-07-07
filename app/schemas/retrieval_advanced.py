"""Request/response schemas for advanced retrieval API (feature-061)."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from app.embedding_pipeline.advanced_retrieval import (
    AdvancedRetrievalResponse as ServiceAdvancedRetrievalResponse,
    AdvancedRetrievalRow as ServiceAdvancedRetrievalRow,
    AdvancedRetrievalTimingsMs as ServiceAdvancedRetrievalTimingsMs,
)
from app.embedding_pipeline.stage_config import (
    StageConfig,
    mode_a_preset,
    mode_b_preset,
    mode_c_preset,
    mode_d_preset,
)

_PRESET_FACTORIES = {
    "A": mode_a_preset,
    "B": mode_b_preset,
    "C": mode_c_preset,
    "D": mode_d_preset,
}


class StageConfigPayload(BaseModel):
    search_mode: Literal["vector", "hybrid"] = "vector"
    rerank: bool = False
    query_transform: bool = False
    routing_enabled: bool = False
    fusion: Literal["rrf", "round_robin"] = "rrf"
    temporal_decay: bool = False

    def to_stage_config(self) -> StageConfig:
        return StageConfig(
            search_mode=self.search_mode,
            rerank=self.rerank,
            query_transform=self.query_transform,
            routing_enabled=self.routing_enabled,
            fusion=self.fusion,
            temporal_decay=self.temporal_decay,
        )


class AdvancedRetrievalRequest(BaseModel):
    query: str = Field(min_length=1)
    preset: Literal["A", "B", "C", "D"] | None = None
    config: StageConfigPayload | None = None
    recall_k: int | None = Field(default=None, ge=1, le=200)
    top_k_final: int | None = Field(default=None, ge=1, le=50)

    @field_validator("query")
    @classmethod
    def strip_query(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("query must not be empty")
        return stripped

    @model_validator(mode="after")
    def preset_or_config_not_both(self) -> AdvancedRetrievalRequest:
        if self.preset is not None and self.config is not None:
            raise ValueError("provide either preset or config, not both")
        return self


def resolve_request_config(request: AdvancedRetrievalRequest) -> StageConfig:
    if request.preset is not None:
        return _PRESET_FACTORIES[request.preset]()
    if request.config is not None:
        return request.config.to_stage_config()
    return mode_a_preset()


class StageConfigResponse(BaseModel):
    search_mode: Literal["vector", "hybrid"]
    rerank: bool
    query_transform: bool
    routing_enabled: bool
    fusion: Literal["rrf", "round_robin"]
    temporal_decay: bool

    @classmethod
    def from_stage_config(cls, config: StageConfig) -> StageConfigResponse:
        return cls(
            search_mode=config.search_mode,
            rerank=config.rerank,
            query_transform=config.query_transform,
            routing_enabled=config.routing_enabled,
            fusion=config.fusion,
            temporal_decay=config.temporal_decay,
        )


class AdvancedRetrievalResultRow(BaseModel):
    final_position: int
    chunk_id: int
    document_id: int
    collection: str
    budget_id: str | None = None
    score: float
    vector_score: float | None = None
    lexical_score: float | None = None
    fusion_score: float | None = None
    rerank_score: float | None = None
    matched_terms: list[str] = Field(default_factory=list)
    source_strategies: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def from_service_row(cls, row: ServiceAdvancedRetrievalRow) -> AdvancedRetrievalResultRow:
        return cls(
            final_position=row.final_position,
            chunk_id=row.chunk_id,
            document_id=row.document_id,
            collection=row.collection,
            budget_id=row.budget_id,
            score=row.score,
            vector_score=row.vector_score,
            lexical_score=row.lexical_score,
            fusion_score=row.fusion_score,
            rerank_score=row.rerank_score,
            matched_terms=list(row.matched_terms),
            source_strategies=list(row.source_strategies),
            metadata=dict(row.metadata),
        )


class AdvancedRetrievalTimingsMs(BaseModel):
    vector: int = 0
    lexical: int = 0
    fusion: int = 0
    rerank: int = 0
    total: int = 0

    @classmethod
    def from_service_timings(
        cls,
        timings: ServiceAdvancedRetrievalTimingsMs,
    ) -> AdvancedRetrievalTimingsMs:
        return cls(
            vector=timings.vector,
            lexical=timings.lexical,
            fusion=timings.fusion,
            rerank=timings.rerank,
            total=timings.total,
        )


class AdvancedRetrievalResponse(BaseModel):
    query: str
    config: StageConfigResponse
    effective_config: StageConfigResponse
    timings_ms: AdvancedRetrievalTimingsMs
    results: list[AdvancedRetrievalResultRow]
    warnings: list[str] = Field(default_factory=list)

    @classmethod
    def from_service_response(
        cls,
        response: ServiceAdvancedRetrievalResponse,
    ) -> AdvancedRetrievalResponse:
        return cls(
            query=response.query,
            config=StageConfigResponse.from_stage_config(response.config),
            effective_config=StageConfigResponse.from_stage_config(response.effective_config),
            timings_ms=AdvancedRetrievalTimingsMs.from_service_timings(response.timings_ms),
            results=[
                AdvancedRetrievalResultRow.from_service_row(row) for row in response.results
            ],
            warnings=list(response.warnings),
        )
