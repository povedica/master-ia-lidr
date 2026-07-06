"""Unit tests for the Redis-backed runtime config service (feature-057)."""

from __future__ import annotations

import json
from typing import Any

import pytest
from redis.exceptions import RedisError

from app.config import Settings
from app.schemas.runtime_config import (
    RuntimeModelConfigUpdate,
    RuntimeRetrievalConfigUpdate,
)
from app.services.runtime_config import (
    MODELS_CONFIG_KEY,
    RETRIEVAL_CONFIG_KEY,
    RuntimeConfigUnavailableError,
    build_redis_client,
    get_effective_models_config,
    get_effective_retrieval_config,
    update_models_config,
    update_retrieval_config,
)


class _FakeRedis:
    """In-memory async Redis double supporting ``get``/``set``."""

    def __init__(self, *, initial: dict[str, str] | None = None) -> None:
        self.store: dict[str, str] = dict(initial or {})

    async def get(self, key: str) -> str | None:
        return self.store.get(key)

    async def set(self, key: str, value: str) -> None:
        self.store[key] = value


class _FailingRedis:
    """Redis double that always raises ``RedisError``."""

    async def get(self, key: str) -> str | None:
        raise RedisError("connection refused")

    async def set(self, key: str, value: str) -> None:
        raise RedisError("connection refused")


def _settings(**overrides: Any) -> Settings:
    return Settings(_env_file=None, **overrides)


class TestBuildRedisClient:
    def test_returns_none_when_redis_url_empty(self) -> None:
        assert build_redis_client(_settings(redis_url="")) is None

    def test_returns_client_when_redis_url_set(self) -> None:
        client = build_redis_client(_settings(redis_url="redis://localhost:6379/0"))
        assert client is not None


class TestEffectiveRetrievalConfig:
    async def test_falls_back_to_settings_without_redis(self) -> None:
        settings = _settings(
            retrieval_rerank_enabled=True,
            retrieval_rerank_model="cross-encoder/mini",
            retrieval_recall_k=42,
            retrieval_top_k_final=7,
        )

        effective = await get_effective_retrieval_config(settings, None)

        assert effective.rerank_enabled is True
        assert effective.rerank_model == "cross-encoder/mini"
        assert effective.recall_k == 42
        assert effective.top_k_final == 7

    async def test_merges_redis_override_over_settings(self) -> None:
        settings = _settings(retrieval_rerank_enabled=True, retrieval_recall_k=50)
        redis_client = _FakeRedis(
            initial={RETRIEVAL_CONFIG_KEY: json.dumps({"rerank_enabled": False})}
        )

        effective = await get_effective_retrieval_config(settings, redis_client)

        assert effective.rerank_enabled is False
        assert effective.recall_k == 50  # untouched field keeps the settings default

    async def test_degrades_to_settings_when_redis_read_fails(self) -> None:
        settings = _settings(retrieval_rerank_enabled=True)

        effective = await get_effective_retrieval_config(settings, _FailingRedis())

        assert effective.rerank_enabled is True

    async def test_degrades_to_settings_when_payload_is_invalid_json(self) -> None:
        settings = _settings(retrieval_rerank_enabled=True)
        redis_client = _FakeRedis(initial={RETRIEVAL_CONFIG_KEY: "not-json"})

        effective = await get_effective_retrieval_config(settings, redis_client)

        assert effective.rerank_enabled is True


class TestUpdateRetrievalConfig:
    async def test_persists_partial_override_and_returns_merged_effective_config(self) -> None:
        settings = _settings(
            retrieval_rerank_enabled=True,
            retrieval_rerank_model="cross-encoder/mini",
        )
        redis_client = _FakeRedis()

        updated = await update_retrieval_config(
            settings,
            redis_client,
            RuntimeRetrievalConfigUpdate(rerank_enabled=False),
        )

        assert updated.rerank_enabled is False
        assert updated.rerank_model == "cross-encoder/mini"
        stored = json.loads(redis_client.store[RETRIEVAL_CONFIG_KEY])
        assert stored == {"rerank_enabled": False}

    async def test_second_partial_update_preserves_earlier_override_fields(self) -> None:
        settings = _settings()
        redis_client = _FakeRedis()
        await update_retrieval_config(
            settings, redis_client, RuntimeRetrievalConfigUpdate(rerank_enabled=False)
        )

        updated = await update_retrieval_config(
            settings, redis_client, RuntimeRetrievalConfigUpdate(recall_k=77)
        )

        assert updated.rerank_enabled is False
        assert updated.recall_k == 77

    async def test_raises_unavailable_when_redis_client_is_none(self) -> None:
        settings = _settings()

        with pytest.raises(RuntimeConfigUnavailableError):
            await update_retrieval_config(
                settings, None, RuntimeRetrievalConfigUpdate(rerank_enabled=False)
            )

    async def test_raises_unavailable_when_redis_write_fails(self) -> None:
        settings = _settings()

        with pytest.raises(RuntimeConfigUnavailableError):
            await update_retrieval_config(
                settings,
                _FailingRedis(),
                RuntimeRetrievalConfigUpdate(rerank_enabled=False),
            )


class TestModelsConfig:
    async def test_effective_models_config_falls_back_to_settings(self) -> None:
        settings = _settings(openai_model="gpt-4o-mini", ragas_judge_model="gpt-4o-mini")

        effective = await get_effective_models_config(settings, None)

        assert effective.structured_model == "gpt-4o-mini"
        assert effective.judge_model == "gpt-4o-mini"

    async def test_update_and_get_round_trip(self) -> None:
        settings = _settings(openai_model="gpt-4o-mini", ragas_judge_model="gpt-4o-mini")
        redis_client = _FakeRedis()

        updated = await update_models_config(
            settings,
            redis_client,
            RuntimeModelConfigUpdate(structured_model="gpt-4.1-mini"),
        )
        assert updated.structured_model == "gpt-4.1-mini"
        assert updated.judge_model == "gpt-4o-mini"

        effective = await get_effective_models_config(settings, redis_client)
        assert effective.structured_model == "gpt-4.1-mini"
        assert json.loads(redis_client.store[MODELS_CONFIG_KEY]) == {
            "structured_model": "gpt-4.1-mini"
        }

    async def test_raises_unavailable_when_redis_client_is_none(self) -> None:
        settings = _settings()

        with pytest.raises(RuntimeConfigUnavailableError):
            await update_models_config(
                settings, None, RuntimeModelConfigUpdate(judge_model="gpt-4.1-mini")
            )
