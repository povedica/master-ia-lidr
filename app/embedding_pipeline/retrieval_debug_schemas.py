"""Pydantic schemas for the internal retrieval debug API."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

SUPPORTED_STRATEGIES = {"all", "vector", "lexical", "hybrid", "rerank"}


class VectorBranchConfig(BaseModel):
    """Configuration for the vector branch of a retrieval debug request."""

    top_k: int = Field(default=10, ge=1, le=50)
    threshold: float | None = Field(default=None, ge=0.0, le=1.0)


class LexicalBranchConfig(BaseModel):
    """Configuration for the lexical full-text branch of a retrieval debug request."""

    top_k: int = Field(default=10, ge=1, le=50)


class HybridBranchConfig(BaseModel):
    """Configuration for the hybrid fusion branch of a retrieval debug request."""

    enabled: bool = True
    method: Literal["rrf", "weighted"] = "rrf"
    rrf_k: int = Field(default=60, ge=1)
    weights: dict[str, float] | None = None

    @model_validator(mode="after")
    def validate_weighted_method_has_weights(self) -> HybridBranchConfig:
        if self.method == "weighted" and not self.weights:
            raise ValueError("hybrid.weights is required when method is 'weighted'")
        return self


class RerankBranchConfig(BaseModel):
    """Configuration for the rerank branch of a retrieval debug request."""

    enabled: bool = False


class RetrievalYearFilter(BaseModel):
    """Inclusive year bounds for retrieval debug metadata filtering."""

    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)

    from_: int | None = Field(default=None, alias="from")
    to: int | None = None

    def is_empty(self) -> bool:
        return self.from_ is None and self.to is None


class RetrievalMetadataFilters(BaseModel):
    """Optional metadata filters applied to retrieval debug branches."""

    model_config = ConfigDict(extra="ignore")

    document_type: str | None = None
    client_sector: str | None = None
    main_technology: str | None = None
    source_name: str | None = None
    language: str | None = None
    tags: list[str] | None = None
    year: RetrievalYearFilter | None = None
    chunk_types: list[str] | None = None
    collection: str | None = None

    @field_validator(
        "document_type",
        "client_sector",
        "main_technology",
        "source_name",
        "language",
        mode="before",
    )
    @classmethod
    def normalize_optional_text(cls, value: object) -> object:
        if isinstance(value, str):
            stripped = value.strip()
            return stripped or None
        return value

    @field_validator("tags", mode="before")
    @classmethod
    def normalize_tags(cls, value: object) -> object:
        if value is None:
            return None
        if not isinstance(value, list):
            return value
        tags = [tag.strip() for tag in value if isinstance(tag, str) and tag.strip()]
        return tags or None

    @model_validator(mode="after")
    def normalize_empty_year(self) -> RetrievalMetadataFilters:
        if self.year is not None and self.year.is_empty():
            self.year = None
        return self

    def is_empty(self) -> bool:
        return not self.model_dump(exclude_none=True)


class RetrievalDebugRequest(BaseModel):
    """Request contract for explainable retrieval diagnostics."""

    query: str
    strategies: list[str] = Field(default_factory=lambda: ["vector"])
    vector: VectorBranchConfig = Field(default_factory=VectorBranchConfig)
    lexical: LexicalBranchConfig = Field(default_factory=LexicalBranchConfig)
    hybrid: HybridBranchConfig = Field(default_factory=HybridBranchConfig)
    rerank: RerankBranchConfig = Field(default_factory=RerankBranchConfig)
    filters: RetrievalMetadataFilters | None = None
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

    @model_validator(mode="after")
    def ignore_empty_filters(self) -> RetrievalDebugRequest:
        if self.filters is not None and self.filters.is_empty():
            self.filters = None
        return self


class BranchResultEntry(BaseModel):
    """One ranked entry emitted by a retrieval branch before fusion."""

    rank: int = Field(ge=1)
    chunk_id: int
    document_id: int
    score: float = Field(ge=0.0, le=1.0)
    distance: float | None = Field(default=None, ge=0.0)
    matched_terms: list[str] = Field(default_factory=list)


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


class RankingDiffEntryResponse(BaseModel):
    """One chunk classified in a ranking diff set."""

    chunk_id: int
    document_id: int
    source_strategies: list[str]
    branch_ranks: dict[str, int]


class RankingMoverResponse(BaseModel):
    """One chunk whose fused rank moved materially from branch rank."""

    chunk_id: int
    document_id: int
    from_rank: int = Field(ge=1)
    to_rank: int = Field(ge=1)
    delta: int = Field(ge=0)


class RankingDiffResponse(BaseModel):
    """Ranking diff exposed by the retrieval debug response."""

    common: list[RankingDiffEntryResponse] = Field(default_factory=list)
    vector_only: list[RankingDiffEntryResponse] = Field(default_factory=list)
    lexical_only: list[RankingDiffEntryResponse] = Field(default_factory=list)
    hybrid_rescued: list[RankingDiffEntryResponse] = Field(default_factory=list)
    big_movers: list[RankingMoverResponse] = Field(default_factory=list)
    dropped_by_threshold: list[RankingDiffEntryResponse] = Field(default_factory=list)
    dropped_by_rerank: list[RankingDiffEntryResponse] = Field(default_factory=list)


class DebugResult(BaseModel):
    """Final result row shown by the retrieval debug endpoint."""

    final_position: int = Field(ge=1)
    chunk_id: int
    document_id: int
    title: str
    content_excerpt: str
    semantic_score: float | None = Field(default=None, ge=0.0, le=1.0)
    semantic_rank: int | None = Field(default=None, ge=1)
    semantic_distance: float | None = Field(default=None, ge=0.0)
    lexical_score: float | None = Field(default=None, ge=0.0, le=1.0)
    lexical_rank: int | None = Field(default=None, ge=1)
    fusion_score: float | None = Field(default=None, ge=0.0, le=1.0)
    fusion_rank: int | None = Field(default=None, ge=1)
    rerank_score: float | None = Field(default=None, ge=0.0, le=1.0)
    rerank_rank: int | None = Field(default=None, ge=1)
    matched_terms: list[str] = Field(default_factory=list)
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
    diff: RankingDiffResponse | None = None


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
    matched_terms: list[str] = Field(default_factory=list)
