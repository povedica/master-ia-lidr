"""Redis-backed runtime configuration overrides (feature-057).

Overrides are stored as small JSON blobs in Redis and merged over env
``Settings`` at read time. When Redis is unreachable or unconfigured, reads
degrade to env defaults (documented fork choice); writes raise
``RuntimeConfigUnavailableError`` so callers can return a safe ``503``.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Protocol

from redis.exceptions import RedisError

from app.config import Settings
from app.schemas.runtime_config import (
    RuntimeModelConfig,
    RuntimeModelConfigUpdate,
    RuntimeRetrievalConfig,
    RuntimeRetrievalConfigUpdate,
)

logger = logging.getLogger(__name__)

RETRIEVAL_CONFIG_KEY = "master-ia:runtime:retrieval"
MODELS_CONFIG_KEY = "master-ia:runtime:models"


class RuntimeConfigUnavailableError(RuntimeError):
    """Raised when a runtime config write cannot reach a configured Redis store."""


class RuntimeConfigRedisClient(Protocol):
    """Minimal async Redis surface used by this service."""

    async def get(self, key: str) -> Any: ...

    async def set(self, key: str, value: str) -> Any: ...


def build_redis_client(settings: Settings) -> RuntimeConfigRedisClient | None:
    """Build an async Redis client from ``Settings.redis_url``, or ``None`` when unset."""

    url = settings.redis_url.strip()
    if not url:
        return None
    from redis.asyncio import Redis

    return Redis.from_url(url, decode_responses=True)


async def _read_override(
    redis_client: RuntimeConfigRedisClient | None, key: str
) -> dict[str, Any]:
    if redis_client is None:
        return {}
    try:
        raw = await redis_client.get(key)
    except RedisError as exc:
        logger.warning(
            "runtime_config.redis_read_failed",
            extra={"key": key, "error_type": type(exc).__name__},
        )
        return {}
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError):
        logger.warning("runtime_config.redis_payload_invalid", extra={"key": key})
        return {}
    return parsed if isinstance(parsed, dict) else {}


async def _write_override(
    redis_client: RuntimeConfigRedisClient | None,
    key: str,
    payload: dict[str, Any],
) -> None:
    if redis_client is None:
        raise RuntimeConfigUnavailableError(
            "Redis is not configured; runtime config cannot be persisted."
        )
    try:
        await redis_client.set(key, json.dumps(payload))
    except RedisError as exc:
        logger.warning(
            "runtime_config.redis_write_failed",
            extra={"key": key, "error_type": type(exc).__name__},
        )
        raise RuntimeConfigUnavailableError(
            "Unable to reach Redis to persist runtime config."
        ) from exc


def _retrieval_from_override(
    settings: Settings, override: dict[str, Any]
) -> RuntimeRetrievalConfig:
    return RuntimeRetrievalConfig(
        rerank_enabled=override.get("rerank_enabled", settings.retrieval_rerank_enabled),
        rerank_model=override.get("rerank_model", settings.retrieval_rerank_model),
        recall_k=override.get("recall_k", settings.retrieval_recall_k),
        top_k_final=override.get("top_k_final", settings.retrieval_top_k_final),
    )


def _models_from_override(settings: Settings, override: dict[str, Any]) -> RuntimeModelConfig:
    return RuntimeModelConfig(
        structured_model=override.get("structured_model", settings.openai_model),
        judge_model=override.get("judge_model", settings.ragas_judge_model),
    )


async def get_effective_retrieval_config(
    settings: Settings,
    redis_client: RuntimeConfigRedisClient | None,
) -> RuntimeRetrievalConfig:
    """Return retrieval config: Redis override merged over env ``Settings``."""

    override = await _read_override(redis_client, RETRIEVAL_CONFIG_KEY)
    return _retrieval_from_override(settings, override)


async def update_retrieval_config(
    settings: Settings,
    redis_client: RuntimeConfigRedisClient | None,
    update: RuntimeRetrievalConfigUpdate,
) -> RuntimeRetrievalConfig:
    """Merge ``update`` into the stored override and persist it to Redis."""

    existing = await _read_override(redis_client, RETRIEVAL_CONFIG_KEY)
    changes = update.model_dump(exclude_none=True)
    merged = {**existing, **changes}
    await _write_override(redis_client, RETRIEVAL_CONFIG_KEY, merged)
    return _retrieval_from_override(settings, merged)


async def get_effective_models_config(
    settings: Settings,
    redis_client: RuntimeConfigRedisClient | None,
) -> RuntimeModelConfig:
    """Return model config: Redis override merged over env ``Settings``."""

    override = await _read_override(redis_client, MODELS_CONFIG_KEY)
    return _models_from_override(settings, override)


async def update_models_config(
    settings: Settings,
    redis_client: RuntimeConfigRedisClient | None,
    update: RuntimeModelConfigUpdate,
) -> RuntimeModelConfig:
    """Merge ``update`` into the stored override and persist it to Redis."""

    existing = await _read_override(redis_client, MODELS_CONFIG_KEY)
    changes = update.model_dump(exclude_none=True)
    merged = {**existing, **changes}
    await _write_override(redis_client, MODELS_CONFIG_KEY, merged)
    return _models_from_override(settings, merged)
