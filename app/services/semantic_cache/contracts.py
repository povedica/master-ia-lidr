"""Typed contracts for semantic cache lookup, writes, and decisions."""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class CacheDecisionStatus(StrEnum):
    """High-level semantic cache decision."""

    disabled = "disabled"
    log_only = "log_only"
    hit = "hit"
    miss = "miss"
    error = "error"


class CacheMissReason(StrEnum):
    """Stable miss / no-serve reason for telemetry and API metadata."""

    disabled = "disabled"
    log_only = "log_only"
    bucket_empty = "bucket_empty"
    no_neighbor = "no_neighbor"
    low_score = "low_score"
    payload_invalid = "payload_invalid"
    guardrail_not_cacheable = "guardrail_not_cacheable"
    store_error = "store_error"
    embedding_error = "embedding_error"
    not_configured = "not_configured"


class SemanticCacheBucket(BaseModel):
    """Deterministic bucket identity (hash + optional human prefix)."""

    model_config = ConfigDict(extra="forbid")

    bucket_hash: str = Field(..., min_length=16, max_length=128)
    namespace: str = Field(..., min_length=1, max_length=128)
    display_key: str = Field(
        ...,
        min_length=1,
        max_length=256,
        description="Safe opaque bucket label for clients (no raw user text).",
    )


class SemanticCacheLookupRequest(BaseModel):
    """Inputs required for a guarded lookup after input guardrails."""

    model_config = ConfigDict(extra="forbid")

    operation: str = Field(..., min_length=1, max_length=64)
    endpoint: str = Field(..., min_length=1, max_length=64)
    tenant_id: str = Field(default="default", min_length=1, max_length=128)
    bucket: SemanticCacheBucket
    vector_text: str = Field(default="", max_length=500_000)
    request_id: str = Field(..., min_length=1, max_length=128)


class CachedEstimationArtifact(BaseModel):
    """Versioned payload persisted for a semantic cache entry."""

    model_config = ConfigDict(extra="forbid")

    cache_schema_version: str = Field(default="1", min_length=1, max_length=16)
    bucket_hash: str = Field(..., min_length=16, max_length=128)
    input_fingerprint: str = Field(..., min_length=16, max_length=128)
    embedding_model: str = Field(..., min_length=1, max_length=128)
    embedding_model_version: str = Field(..., min_length=1, max_length=128)
    prompt_version: str = Field(..., min_length=1, max_length=128)
    examples_version: str = Field(..., min_length=1, max_length=128)
    output_schema_version: str = Field(default="1", min_length=1, max_length=32)
    guardrail_rules_version: str = Field(..., min_length=1, max_length=64)
    provider: str = Field(..., min_length=1, max_length=64)
    model: str = Field(..., min_length=1, max_length=128)
    mode: str = Field(..., min_length=1, max_length=32)
    result: dict[str, Any] = Field(..., description="Validated EstimationResult JSON.")
    assessment: dict[str, Any]
    mode_eligibility: dict[str, Any]
    usage: dict[str, Any] | None = None
    finish_reason: str | None = Field(default=None, max_length=64)
    safe_to_cache: bool = True
    safe_to_display: bool = True
    degraded: bool = False


class SemanticCacheEntry(BaseModel):
    """Stored neighbor: vector id, score (filled after query), and artifact."""

    model_config = ConfigDict(extra="forbid")

    entry_id: str = Field(..., min_length=8, max_length=128)
    bucket_hash: str = Field(..., min_length=16, max_length=128)
    similarity: float = Field(default=0.0, ge=-1.0, le=1.0)
    artifact: CachedEstimationArtifact


class SemanticCacheWriteRequest(BaseModel):
    """Validated write after output guardrails."""

    model_config = ConfigDict(extra="forbid")

    lookup: SemanticCacheLookupRequest
    embedding: list[float] = Field(..., min_length=1)
    artifact: CachedEstimationArtifact


class CacheLookupResult(BaseModel):
    """Outcome of a single semantic lookup."""

    model_config = ConfigDict(extra="forbid")

    status: CacheDecisionStatus
    miss_reason: CacheMissReason | None = None
    top_score: float | None = Field(default=None, ge=-1.0, le=1.0)
    bucket: SemanticCacheBucket | None = None
    entry: SemanticCacheEntry | None = None
    would_hit: bool = Field(
        default=False,
        description="True when score >= threshold regardless of log-only / disabled serving.",
    )


class CacheWriteDecision(BaseModel):
    """Whether a write was attempted or skipped."""

    model_config = ConfigDict(extra="forbid")

    wrote: bool = False
    skip_reason: str | None = Field(default=None, max_length=128)
