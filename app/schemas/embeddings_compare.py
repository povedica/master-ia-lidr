"""HTTP schemas for chunking compare API (feature-063)."""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator

from app.embedding_pipeline.schemas import Budget


class EmbeddingsCompareRequest(BaseModel):
    budgets: list[Budget] = Field(min_length=1)
    strategies: list[str] | None = None
    queries: list[str] = Field(default_factory=list)
    top_k: int = Field(default=3, ge=1, le=10)

    @field_validator("strategies")
    @classmethod
    def normalize_strategies(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        normalized = [item.strip() for item in value if item.strip()]
        return normalized or None


class StrategyStatsView(BaseModel):
    strategy: str
    chunk_count: int
    avg_chunk_chars: int
    total_tokens_estimate: int
    estimated_embedding_cost_usd: float


class StrategyQueryPreviewView(BaseModel):
    strategy: str
    query: str
    top_chunks: list[dict[str, object]]


class EmbeddingsCompareResponse(BaseModel):
    stats_per_strategy: list[StrategyStatsView]
    queries_per_strategy: list[StrategyQueryPreviewView] = Field(default_factory=list)
