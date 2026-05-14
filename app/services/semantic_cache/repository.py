"""Semantic cache storage (protocol + in-process implementations)."""

from __future__ import annotations

import json
import math
import struct
import time
import uuid
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from redis.asyncio import Redis
from redis.exceptions import ResponseError

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


class RedisSemanticCacheRepository:
    """Redis Stack / RediSearch implementation of the semantic cache repository."""

    _VECTOR_FIELD = "embedding"
    _ARTIFACT_FIELD = "artifact_json"

    def __init__(
        self,
        *,
        redis_client: Redis,
        namespace: str,
        vector_dimensions: int | None = None,
    ) -> None:
        self._redis = redis_client
        self._namespace = namespace.strip() or "semantic:estimation"
        self._index_name = f"{self._namespace}:idx"
        self._key_prefix = f"{self._namespace}:entry:"
        self._index_ready_dimensions = vector_dimensions

    @classmethod
    def from_url(cls, *, redis_url: str, namespace: str) -> "RedisSemanticCacheRepository":
        """Build a repository using Redis' async client."""

        return cls(
            redis_client=Redis.from_url(redis_url, decode_responses=False),
            namespace=namespace,
        )

    async def nearest_neighbors(
        self,
        *,
        bucket_hash: str,
        query_vector: list[float],
        k: int,
    ) -> list[SemanticCacheEntry]:
        if not query_vector or k <= 0:
            return []

        await self._ensure_index(vector_dimensions=len(query_vector))
        query = (
            f"@bucket_hash:{{{_escape_redis_tag(bucket_hash)}}}"
            f"=>[KNN {k} @{self._VECTOR_FIELD} $vector AS vector_distance]"
        )
        raw = await self._redis.execute_command(
            "FT.SEARCH",
            self._index_name,
            query,
            "PARAMS",
            "2",
            "vector",
            _float32_bytes(query_vector),
            "RETURN",
            "4",
            "entry_id",
            "bucket_hash",
            self._ARTIFACT_FIELD,
            "vector_distance",
            "SORTBY",
            "vector_distance",
            "ASC",
            "DIALECT",
            "2",
        )
        return _parse_search_results(raw)

    async def write(self, payload: SemanticCacheWriteRequest, *, ttl_seconds: int) -> None:
        await self._ensure_index(vector_dimensions=len(payload.embedding))
        entry_id = uuid.uuid4().hex
        key = f"{self._key_prefix}{entry_id}"
        artifact_json = payload.artifact.model_dump_json()
        await self._redis.hset(
            key,
            mapping={
                "entry_id": entry_id,
                "bucket_hash": payload.lookup.bucket.bucket_hash,
                self._ARTIFACT_FIELD: artifact_json,
                self._VECTOR_FIELD: _float32_bytes(payload.embedding),
            },
        )
        await self._redis.expire(key, ttl_seconds)

    async def _ensure_index(self, *, vector_dimensions: int) -> None:
        if self._index_ready_dimensions == vector_dimensions:
            return

        try:
            await self._redis.execute_command("FT.INFO", self._index_name)
        except ResponseError as exc:
            message = str(exc).lower()
            if "unknown index" not in message and "no such index" not in message:
                raise
            await self._create_index(vector_dimensions=vector_dimensions)

        self._index_ready_dimensions = vector_dimensions

    async def _create_index(self, *, vector_dimensions: int) -> None:
        await self._redis.execute_command(
            "FT.CREATE",
            self._index_name,
            "ON",
            "HASH",
            "PREFIX",
            "1",
            self._key_prefix,
            "SCHEMA",
            "entry_id",
            "TAG",
            "bucket_hash",
            "TAG",
            self._ARTIFACT_FIELD,
            "TEXT",
            self._VECTOR_FIELD,
            "VECTOR",
            "FLAT",
            "6",
            "TYPE",
            "FLOAT32",
            "DIM",
            vector_dimensions,
            "DISTANCE_METRIC",
            "COSINE",
        )


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


def _float32_bytes(values: list[float]) -> bytes:
    return struct.pack(f"<{len(values)}f", *values)


_REDIS_TAG_ESCAPED_CHARS = {
    ",",
    ".",
    "<",
    ">",
    "{",
    "}",
    "[",
    "]",
    '"',
    "'",
    ":",
    ";",
    "!",
    "@",
    "#",
    "$",
    "%",
    "^",
    "&",
    "*",
    "(",
    ")",
    "-",
    "+",
    "=",
    "~",
    " ",
}


def _escape_redis_tag(value: str) -> str:
    return "".join(f"\\{char}" if char in _REDIS_TAG_ESCAPED_CHARS else char for char in value)


def _parse_search_results(raw: Any) -> list[SemanticCacheEntry]:
    if not isinstance(raw, list) or len(raw) < 2:
        return []

    entries: list[SemanticCacheEntry] = []
    parts = raw[1:]
    for idx in range(0, len(parts), 2):
        fields = parts[idx + 1] if idx + 1 < len(parts) else []
        if not isinstance(fields, list):
            continue

        row = _field_pairs_to_dict(fields)
        artifact_raw = row.get("artifact_json")
        if artifact_raw is None:
            continue

        artifact = CachedEstimationArtifact.model_validate_json(artifact_raw)
        distance = _to_float(row.get("vector_distance"), default=1.0)
        similarity = max(-1.0, min(1.0, 1.0 - distance))
        entry_id = row.get("entry_id") or _decode_text(parts[idx])
        bucket_hash = row.get("bucket_hash") or artifact.bucket_hash
        entries.append(
            SemanticCacheEntry(
                entry_id=entry_id,
                bucket_hash=bucket_hash,
                similarity=similarity,
                artifact=artifact,
            )
        )

    entries.sort(key=lambda e: e.similarity, reverse=True)
    return entries


def _field_pairs_to_dict(fields: list[Any]) -> dict[str, str]:
    out: dict[str, str] = {}
    for idx in range(0, len(fields), 2):
        if idx + 1 >= len(fields):
            continue
        out[_decode_text(fields[idx])] = _decode_text(fields[idx + 1])
    return out


def _decode_text(value: Any) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8")
    return str(value)


def _to_float(value: Any, *, default: float) -> float:
    if value is None:
        return default
    try:
        return float(_decode_text(value))
    except ValueError:
        return default


def json_serialized_size_bytes(obj: Any) -> int:
    raw = json.dumps(obj, separators=(",", ":"), default=str).encode("utf-8")
    return len(raw)
