"""Semantic cache storage (protocol + in-process implementations)."""

from __future__ import annotations

import json
import math
import time
import uuid
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from app.services.semantic_cache.contracts import (
    CachedEstimationArtifact,
    SemanticCacheEntry,
    SemanticCacheWriteRequest,
)


@runtime_checkable
class SemanticCacheRepository(Protocol):
    """Vector-ish neighbor search scoped to a bucket."""

    async def nearest_neighbors(
        self,
        *,
        bucket_hash: str,
        query_vector: list[float],
        k: int,
    ) -> list[SemanticCacheEntry]:
        """Return up to ``k`` neighbors ordered by descending similarity."""
        ...

    async def write(self, payload: SemanticCacheWriteRequest, *, ttl_seconds: int) -> None:
        """Persist a validated entry under its bucket."""
        ...


@dataclass
class _StoredRow:
    entry_id: str
    bucket_hash: str
    vector: list[float]
    artifact: CachedEstimationArtifact
    expires_at: float


class InMemorySemanticCacheRepository:
    """Single-process vector store with cosine similarity (for tests and local demos)."""

    def __init__(self) -> None:
        self._rows: list[_StoredRow] = []

    async def nearest_neighbors(
        self,
        *,
        bucket_hash: str,
        query_vector: list[float],
        k: int,
    ) -> list[SemanticCacheEntry]:
        now = time.time()
        scored: list[tuple[float, _StoredRow]] = []
        for row in self._rows:
            if row.bucket_hash != bucket_hash:
                continue
            if row.expires_at <= now:
                continue
            sim = _cosine_similarity(query_vector, row.vector)
            scored.append((sim, row))
        scored.sort(key=lambda t: t[0], reverse=True)
        out: list[SemanticCacheEntry] = []
        for sim, row in scored[:k]:
            out.append(
                SemanticCacheEntry(
                    entry_id=row.entry_id,
                    bucket_hash=row.bucket_hash,
                    similarity=sim,
                    artifact=row.artifact,
                )
            )
        return out

    async def write(self, payload: SemanticCacheWriteRequest, *, ttl_seconds: int) -> None:
        now = time.time()
        entry_id = uuid.uuid4().hex
        row = _StoredRow(
            entry_id=entry_id,
            bucket_hash=payload.lookup.bucket.bucket_hash,
            vector=list(payload.embedding),
            artifact=payload.artifact,
            expires_at=now + float(ttl_seconds),
        )
        self._rows.append(row)
        self._prune_expired(now)

    def _prune_expired(self, now: float) -> None:
        self._rows = [r for r in self._rows if r.expires_at > now]


class NullSemanticCacheRepository:
    """No-op store (always empty)."""

    async def nearest_neighbors(
        self,
        *,
        bucket_hash: str,
        query_vector: list[float],
        k: int,
    ) -> list[SemanticCacheEntry]:
        del bucket_hash, query_vector, k
        return []

    async def write(self, payload: SemanticCacheWriteRequest, *, ttl_seconds: int) -> None:
        del payload, ttl_seconds
        return None


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    if len(a) != len(b) or not a:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / (na * nb)


def json_serialized_size_bytes(obj: Any) -> int:
    raw = json.dumps(obj, separators=(",", ":"), default=str).encode("utf-8")
    return len(raw)
