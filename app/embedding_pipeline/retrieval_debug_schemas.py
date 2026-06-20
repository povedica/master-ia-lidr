"""Pydantic schemas for the internal retrieval debug API."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

SUPPORTED_STRATEGIES = {"all", "vector", "lexical", "hybrid", "rerank"}


class VectorBranchConfig(BaseModel):
    """Configuration for the vector branch of a retrieval debug request."""

    top_k: int = Field(default=10, ge=1, le=50)
    threshold: float | None = Field(default=None, ge=0.0, le=1.0)


class RetrievalDebugRequest(BaseModel):
    """Request contract for explainable retrieval diagnostics."""

    query: str
    strategies: list[str] = Field(default_factory=lambda: ["vector"])
    vector: VectorBranchConfig = Field(default_factory=VectorBranchConfig)
    max_results: int = Field(default=10, ge=1, le=50)

    @field_validator("query")
    @classmethod
    def validate_query_not_empty(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("query must not be empty")
        return stripped

    @field_validator("strategies")
    @classmethod
    def validate_strategies(cls, value: list[str]) -> list[str]:
        if not value:
            raise ValueError("strategies must not be empty")
        normalized = [strategy.strip().lower() for strategy in value]
        invalid = [strategy for strategy in normalized if strategy not in SUPPORTED_STRATEGIES]
        if invalid:
            raise ValueError(f"unsupported retrieval strategies: {', '.join(invalid)}")
        if "all" in normalized and len(normalized) > 1:
            raise ValueError("'all' cannot be combined with explicit strategies")
        return normalized


class BranchResultEntry(BaseModel):
    """One ranked entry emitted by a retrieval branch before fusion."""

    rank: int = Field(ge=1)
    chunk_id: int
    document_id: int
    score: float = Field(ge=0.0, le=1.0)
    distance: float = Field(ge=0.0)


class BranchesContainer(BaseModel):
    """Nullable branch buckets so future strategies can plug into one shape."""

    vector: list[BranchResultEntry] | None = None
    lexical: list[BranchResultEntry] | None = None
    hybrid: list[BranchResultEntry] | None = None
    rerank: list[BranchResultEntry] | None = None


class ResultExplanation(BaseModel):
    """Structured explanation using a controlled signal vocabulary."""

    summary: str
    signals: list[str]


class DebugResult(BaseModel):
    """Final result row shown by the retrieval debug endpoint."""

    final_position: int = Field(ge=1)
    chunk_id: int
    document_id: int
    title: str
    content_excerpt: str
    semantic_score: float = Field(ge=0.0, le=1.0)
    semantic_rank: int = Field(ge=1)
    semantic_distance: float = Field(ge=0.0)
    source_strategies: list[str]
    metadata: dict[str, Any]
    explanation: ResultExplanation


class RetrievalDebugResponse(BaseModel):
    """Response contract for the retrieval debug endpoint."""

    query: str
    applied_config: dict[str, Any]
    timings_ms: dict[str, int]
    warnings: list[str]
    branches: BranchesContainer
    final_results: list[DebugResult]


class ChunkInspectionResponse(BaseModel):
    """Response contract for inspecting one persisted chunk and its context."""

    model_config = ConfigDict(arbitrary_types_allowed=False)

    chunk_id: int
    document_id: int
    content: str
    chunk_type: str
    metadata: dict[str, Any]
    embedding_model: str
    embedding_present: bool
    document: dict[str, Any]
    previous_chunk: dict[str, Any] | None
    next_chunk: dict[str, Any] | None
    distance: float | None = None
    similarity: float | None = None
