"""Idempotency cache for RAG estimate responses (feature-062)."""

from __future__ import annotations

import logging
import threading
import time
from typing import Any

from app.schemas.rag_estimation_response import RagEstimationResponse

logger = logging.getLogger(__name__)

_KEY_PREFIX = "idempotency:rag-estimate:"
_shared_store: IdempotencyStore | None = None
_shared_store_lock = threading.Lock()


def get_idempotency_store(settings) -> IdempotencyStore:
    """Process-wide idempotency store (memory or Redis per settings)."""

    global _shared_store
    if _shared_store is None:
        with _shared_store_lock:
            if _shared_store is None:
                _shared_store = IdempotencyStore.from_settings(settings)
    return _shared_store


def reset_idempotency_store() -> None:
    """Test helper to clear the process-wide store."""

    global _shared_store
    with _shared_store_lock:
        _shared_store = None


class IdempotencyStore:
    """Store ``RagEstimationResponse`` bodies keyed by client idempotency key."""

    def __init__(self, redis_client: Any | None, ttl_seconds: int) -> None:
        self._redis = redis_client
        self._ttl = ttl_seconds
        self._mem: dict[str, tuple[str, float]] = {}
        self._lock = threading.Lock()

    @classmethod
    def from_settings(cls, settings) -> IdempotencyStore:
        redis_client = None
        redis_url = settings.redis_url.strip()
        if redis_url:
            try:
                import redis

                redis_client = redis.from_url(redis_url, decode_responses=True)
                redis_client.ping()
            except Exception as exc:
                logger.warning(
                    "idempotency_redis_unavailable",
                    extra={"error_type": type(exc).__name__},
                )
                redis_client = None
        return cls(redis_client=redis_client, ttl_seconds=settings.rag_idempotency_ttl_seconds)

    def get(self, key: str) -> RagEstimationResponse | None:
        raw = self._get_raw(key)
        if raw is None:
            return None
        try:
            return RagEstimationResponse.model_validate_json(raw)
        except Exception:
            self.delete(key)
            return None

    def set(self, key: str, response: RagEstimationResponse) -> None:
        raw = response.model_dump_json()
        if self._redis is not None:
            self._redis.set(_KEY_PREFIX + key, raw, ex=self._ttl)
            return
        with self._lock:
            self._mem[key] = (raw, time.monotonic() + self._ttl)

    def delete(self, key: str) -> None:
        if self._redis is not None:
            self._redis.delete(_KEY_PREFIX + key)
            return
        with self._lock:
            self._mem.pop(key, None)

    def _get_raw(self, key: str) -> str | None:
        if self._redis is not None:
            return self._redis.get(_KEY_PREFIX + key)
        with self._lock:
            entry = self._mem.get(key)
            if entry is None:
                return None
            raw, expires_at = entry
            if time.monotonic() >= expires_at:
                self._mem.pop(key, None)
                return None
            return raw
