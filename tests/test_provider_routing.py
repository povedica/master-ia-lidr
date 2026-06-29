"""Unit tests for shared LiteLLM provider route resolution."""

from __future__ import annotations

from app.services.llm_chain import LitellmChainProvider
from app.services.llm_types import LLMProvider
from app.services.provider_routing import ProviderRoute, resolve_first_litellm_route


class _NonLitellmProvider:
    name = "static-fallback"

    async def complete(self, system_prompt: str, user_prompt: str, *, max_output_tokens: int):
        raise NotImplementedError


def test_resolve_first_litellm_route_returns_first_litellm_provider() -> None:
    litellm = LitellmChainProvider(
        name="openai",
        litellm_model="gpt-4o-mini",
        api_key="test-key",
        timeout_seconds=30.0,
    )
    providers: list[LLMProvider] = [_NonLitellmProvider(), litellm]  # type: ignore[list-item]

    route = resolve_first_litellm_route(providers)

    assert route == ProviderRoute(
        litellm_model="gpt-4o-mini",
        api_key="test-key",
        timeout_seconds=30.0,
        provider_name="openai",
        model="gpt-4o-mini",
    )


def test_resolve_first_litellm_route_returns_none_when_no_litellm_provider() -> None:
    providers: list[LLMProvider] = [_NonLitellmProvider()]  # type: ignore[list-item]

    assert resolve_first_litellm_route(providers) is None
