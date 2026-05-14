"""Semantic cache settings defaults and helpers."""

from __future__ import annotations

import pytest

from app.config import Settings


_SEMANTIC_CACHE_ENV_VARS = [
    "SEMANTIC_CACHE_ENABLED",
    "SEMANTIC_CACHE_LOG_ONLY",
    "SEMANTIC_CACHE_REDIS_URL",
    "SEMANTIC_CACHE_NAMESPACE",
    "SEMANTIC_CACHE_TTL_SECONDS",
    "SEMANTIC_CACHE_SIMILARITY_THRESHOLD",
    "SEMANTIC_CACHE_MAX_CANDIDATES",
    "SEMANTIC_CACHE_USE_MEMORY_STORE",
]


def _settings(**overrides: object) -> Settings:
    return Settings(_env_file=None, **overrides)


def test_semantic_cache_defaults_match_feature_spec(monkeypatch: pytest.MonkeyPatch) -> None:
    for env_var in _SEMANTIC_CACHE_ENV_VARS:
        monkeypatch.delenv(env_var, raising=False)
    s = _settings()
    assert s.semantic_cache_enabled is False
    assert s.semantic_cache_log_only is True
    assert s.semantic_cache_redis_url == ""
    assert s.semantic_cache_namespace == "semantic:estimation"
    assert s.semantic_cache_ttl_seconds == 86_400
    assert s.semantic_cache_similarity_threshold == 0.92
    assert s.semantic_cache_max_candidates == 5
    assert s.semantic_cache_fully_off() is False
    assert s.semantic_cache_feature_active() is True


def test_semantic_cache_fully_off_skips_feature() -> None:
    s = _settings(semantic_cache_enabled=False, semantic_cache_log_only=False)
    assert s.semantic_cache_fully_off() is True
    assert s.semantic_cache_feature_active() is False


def test_semantic_cache_endpoint_allowlist() -> None:
    s = _settings(semantic_cache_enabled_endpoints="api_v2_estimate,other")
    assert s.semantic_cache_allowed_endpoint("api_v2_estimate") is True
    assert s.semantic_cache_allowed_endpoint("unknown") is False


def test_semantic_cache_tenant_allowlist_empty_means_all() -> None:
    s = _settings(semantic_cache_enabled_tenants="")
    assert s.semantic_cache_allowed_tenant("any") is True


def test_semantic_cache_tenant_allowlist_restricts() -> None:
    s = _settings(semantic_cache_enabled_tenants="a,b")
    assert s.semantic_cache_allowed_tenant("a") is True
    assert s.semantic_cache_allowed_tenant("c") is False
