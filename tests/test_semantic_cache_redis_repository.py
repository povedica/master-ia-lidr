"""Redis semantic cache repository tests with mocked Redis I/O."""

from __future__ import annotations

from typing import Any

import pytest
from redis.exceptions import ResponseError

from app.config import Settings
from app.services.semantic_cache.contracts import (
    CachedEstimationArtifact,
    SemanticCacheBucket,
    SemanticCacheLookupRequest,
    SemanticCacheWriteRequest,
)
from app.services.semantic_cache.factory import build_semantic_cache_service
from app.services.semantic_cache.repository import RedisSemanticCacheRepository


class _FakeRedis:
    def __init__(self, *, search_result: list[Any] | None = None) -> None:
        self.commands: list[tuple[Any, ...]] = []
        self.hsets: list[tuple[str, dict[str, Any]]] = []
        self.expires: list[tuple[str, int]] = []
        self.search_result = search_result

    async def execute_command(self, *args: Any) -> list[Any]:
        self.commands.append(args)
        if args[0] == "FT.INFO":
            raise ResponseError("Unknown Index name")
        if args[0] == "FT.SEARCH":
            return self.search_result or [0]
        return []

    async def hset(self, key: str, *, mapping: dict[str, Any]) -> None:
        self.hsets.append((key, mapping))

    async def expire(self, key: str, ttl_seconds: int) -> None:
        self.expires.append((key, ttl_seconds))


def _artifact(bucket_hash: str) -> CachedEstimationArtifact:
    return CachedEstimationArtifact(
        bucket_hash=bucket_hash,
        input_fingerprint="f" * 64,
        embedding_model="text-embedding-3-small",
        embedding_model_version="text-embedding-3-small:default",
        prompt_version="estimation/v1",
        examples_version="examples/v1",
        guardrail_rules_version="registry-default",
        provider="openai",
        model="gpt-4o-mini",
        mode="standard",
        result={"title": "Cached estimate"},
        assessment={},
        mode_eligibility={},
        finish_reason="stop",
    )


def _write_request(bucket_hash: str = "a" * 64) -> SemanticCacheWriteRequest:
    bucket = SemanticCacheBucket(
        bucket_hash=bucket_hash,
        namespace="semantic:test",
        display_key=f"semantic:test:{bucket_hash[:16]}",
    )
    lookup = SemanticCacheLookupRequest(
        operation="estimation_v2",
        endpoint="api_v2_estimate",
        bucket=bucket,
        vector_text="same intent",
        request_id="req_redis_test",
    )
    return SemanticCacheWriteRequest(
        lookup=lookup,
        embedding=[0.25, 0.75],
        artifact=_artifact(bucket_hash),
    )


@pytest.mark.asyncio
async def test_redis_repository_write_creates_index_and_sets_ttl() -> None:
    fake = _FakeRedis()
    repo = RedisSemanticCacheRepository(redis_client=fake, namespace="semantic:test")
    payload = _write_request()

    await repo.write(payload, ttl_seconds=123)

    assert fake.commands[0] == ("FT.INFO", "semantic:test:idx")
    create_command = fake.commands[1]
    assert create_command[:2] == ("FT.CREATE", "semantic:test:idx")
    assert "DIM" in create_command
    assert create_command[create_command.index("DIM") + 1] == 2
    assert len(fake.hsets) == 1
    key, mapping = fake.hsets[0]
    assert key.startswith("semantic:test:entry:")
    assert mapping["bucket_hash"] == payload.lookup.bucket.bucket_hash
    assert mapping["artifact_json"] == payload.artifact.model_dump_json()
    assert isinstance(mapping["embedding"], bytes)
    assert len(mapping["embedding"]) == 8
    assert fake.expires == [(key, 123)]


@pytest.mark.asyncio
async def test_redis_repository_lookup_filters_by_bucket_and_converts_distance_to_similarity() -> None:
    bucket_hash = "b" * 64
    artifact_json = _artifact(bucket_hash).model_dump_json().encode("utf-8")
    fake = _FakeRedis(
        search_result=[
            1,
            b"semantic:test:entry:stored",
            [
                b"entry_id",
                b"entry1234",
                b"bucket_hash",
                bucket_hash.encode("utf-8"),
                b"artifact_json",
                artifact_json,
                b"vector_distance",
                b"0.12",
            ],
        ],
    )
    repo = RedisSemanticCacheRepository(redis_client=fake, namespace="semantic:test")

    entries = await repo.nearest_neighbors(bucket_hash=bucket_hash, query_vector=[0.1, 0.2], k=3)

    search_command = fake.commands[2]
    assert search_command[:2] == ("FT.SEARCH", "semantic:test:idx")
    assert f"@bucket_hash:{{{bucket_hash}}}" in search_command[2]
    assert entries[0].entry_id == "entry1234"
    assert entries[0].bucket_hash == bucket_hash
    assert entries[0].similarity == pytest.approx(0.88)


def test_factory_uses_redis_repository_when_url_is_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    built: dict[str, str] = {}
    redis_repo = RedisSemanticCacheRepository(redis_client=_FakeRedis(), namespace="semantic:test")

    def _from_url(*, redis_url: str, namespace: str) -> RedisSemanticCacheRepository:
        built["redis_url"] = redis_url
        built["namespace"] = namespace
        return redis_repo

    monkeypatch.setattr(RedisSemanticCacheRepository, "from_url", staticmethod(_from_url))
    settings = Settings(
        _env_file=None,
        semantic_cache_enabled=True,
        semantic_cache_log_only=False,
        semantic_cache_redis_url="redis://example:6379/0",
        semantic_cache_namespace="semantic:test",
        semantic_cache_use_memory_store=False,
    )

    service = build_semantic_cache_service(settings)

    assert service is not None
    assert service._repository is redis_repo  # noqa: SLF001 - verifies factory wiring.
    assert built == {"redis_url": "redis://example:6379/0", "namespace": "semantic:test"}


def test_factory_reuses_single_process_memory_repository() -> None:
    settings = Settings(
        _env_file=None,
        semantic_cache_enabled=True,
        semantic_cache_log_only=False,
        semantic_cache_use_memory_store=True,
        semantic_cache_redis_url="",
    )

    first = build_semantic_cache_service(settings)
    second = build_semantic_cache_service(settings)

    assert first is not None
    assert second is not None
    assert first._repository is second._repository  # noqa: SLF001 - verifies local cache survives requests.
