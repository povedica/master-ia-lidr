"""Semantic cache settings defaults and helpers."""

from __future__ import annotations

from app.config import Settings


def test_semantic_cache_defaults_match_feature_spec() -> None:
    s = Settings()
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
    s = Settings(semantic_cache_enabled=False, semantic_cache_log_only=False)
    assert s.semantic_cache_fully_off() is True
    assert s.semantic_cache_feature_active() is False


def test_semantic_cache_endpoint_allowlist() -> None:
    s = Settings(semantic_cache_enabled_endpoints="api_v2_estimate,other")
    assert s.semantic_cache_allowed_endpoint("api_v2_estimate") is True
    assert s.semantic_cache_allowed_endpoint("unknown") is False


def test_semantic_cache_tenant_allowlist_empty_means_all() -> None:
    s = Settings(semantic_cache_enabled_tenants="")
    assert s.semantic_cache_allowed_tenant("any") is True


def test_semantic_cache_tenant_allowlist_restricts() -> None:
    s = Settings(semantic_cache_enabled_tenants="a,b")
    assert s.semantic_cache_allowed_tenant("a") is True
    assert s.semantic_cache_allowed_tenant("c") is False
