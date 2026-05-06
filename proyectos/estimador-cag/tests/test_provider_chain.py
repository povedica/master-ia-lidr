"""Tests for provider chain configuration and ordering."""

import pytest

from app.config import Settings
from app.services.llm_chain import build_provider_chain
from app.services.llm_types import ProviderConfigError


def test_build_provider_chain_respects_llm_providers_order() -> None:
    settings = Settings(
        llm_providers="anthropic,openai",
        openai_api_key="sk-test",
        anthropic_api_key="ak-test",
        static_fallback_enabled=False,
    )
    chain = build_provider_chain(settings)
    assert [provider.name for provider in chain] == ["anthropic", "openai"]


def test_build_provider_chain_skips_unconfigured_provider() -> None:
    settings = Settings(
        llm_providers="openai,anthropic",
        openai_api_key="",
        anthropic_api_key="ak-test",
        static_fallback_enabled=False,
    )
    chain = build_provider_chain(settings)
    assert [provider.name for provider in chain] == ["anthropic"]


def test_build_provider_chain_ignores_unknown_provider_names() -> None:
    settings = Settings(
        llm_providers="unknown,openai",
        openai_api_key="sk-test",
        static_fallback_enabled=False,
    )
    chain = build_provider_chain(settings)
    assert [provider.name for provider in chain] == ["openai"]


def test_build_provider_chain_adds_static_fallback_at_end() -> None:
    settings = Settings(
        llm_providers="openai",
        openai_api_key="sk-test",
        static_fallback_enabled=True,
    )
    chain = build_provider_chain(settings)
    assert [provider.name for provider in chain] == ["openai", "static_fallback"]


def test_build_provider_chain_raises_when_empty_and_static_disabled() -> None:
    settings = Settings(
        llm_providers="openai,anthropic",
        openai_api_key="",
        anthropic_api_key="",
        static_fallback_enabled=False,
    )
    with pytest.raises(ProviderConfigError, match="No provider could be configured"):
        build_provider_chain(settings)
