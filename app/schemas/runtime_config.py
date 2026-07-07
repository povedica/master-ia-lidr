"""Request/response schemas for Redis-backed runtime configuration (feature-057)."""

from __future__ import annotations

from pydantic import BaseModel, Field


class RuntimeRetrievalConfig(BaseModel):
    """Effective retrieval configuration: Redis override merged over env ``Settings``."""

    rerank_enabled: bool
    rerank_model: str
    recall_k: int
    top_k_final: int


class RuntimeRetrievalConfigUpdate(BaseModel):
    """Partial override for retrieval config; unset fields keep their current value."""

    rerank_enabled: bool | None = None
    rerank_model: str | None = None
    recall_k: int | None = Field(default=None, ge=1, le=200)
    top_k_final: int | None = Field(default=None, ge=1, le=50)


class RuntimeModelConfig(BaseModel):
    """Effective model configuration: Redis override merged over env ``Settings``."""

    structured_model: str
    judge_model: str


class RuntimeModelConfigUpdate(BaseModel):
    """Partial override for model config; unset fields keep their current value."""

    structured_model: str | None = None
    judge_model: str | None = None
