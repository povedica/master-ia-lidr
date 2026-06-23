"""Production retrieval request/response schemas (feature-050)."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


class RetrievalRequest(BaseModel):
    """Lean production retrieval request."""

    query: str = Field(min_length=1)
    mode: Literal["A", "B", "C", "D"] | None = None
    top_k_final: int | None = Field(default=None, ge=1, le=50)
    recall_k: int | None = Field(default=None, ge=1, le=200)

    @field_validator("query")
    @classmethod
    def strip_query(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("query must not be empty")
        return stripped


class RetrievalFusionConfig(BaseModel):
    method: Literal["rrf"] = "rrf"
    rrf_k: int


class RetrievalRerankConfig(BaseModel):
    enabled: bool
    model: str
    is_noop: bool


class RetrievalAppliedConfig(BaseModel):
    mode: Literal["A", "B", "C", "D"]
    branches: list[str]
    fusion: RetrievalFusionConfig | None = None
    rerank: RetrievalRerankConfig
    recall_k: int
    top_k_final: int
    text_search_config: str


class RetrievalTimingsMs(BaseModel):
    vector: int = 0
    lexical: int = 0
    fusion: int = 0
    rerank: int = 0
    total: int = 0


class RetrievalResultRow(BaseModel):
    final_position: int
    chunk_id: int
    document_id: int
    budget_id: str | None = None
    score: float
    vector_score: float | None = None
    lexical_score: float | None = None
    fusion_score: float | None = None
    rerank_score: float | None = None
    matched_terms: list[str] = Field(default_factory=list)
    source_strategies: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class RetrievalResponse(BaseModel):
    query: str
    mode: Literal["A", "B", "C", "D"]
    applied_config: RetrievalAppliedConfig
    timings_ms: RetrievalTimingsMs
    results: list[RetrievalResultRow]
    warnings: list[str] = Field(default_factory=list)
