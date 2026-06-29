"""Shared LiteLLM provider route resolution for structured completions."""

from __future__ import annotations

from dataclasses import dataclass

from app.services.llm_chain import LitellmChainProvider
from app.services.llm_types import LLMProvider


@dataclass(frozen=True)
class ProviderRoute:
    """Resolved LiteLLM credentials and metadata for structured completions."""

    litellm_model: str
    api_key: str
    timeout_seconds: float
    provider_name: str
    model: str


def resolve_first_litellm_route(providers: list[LLMProvider]) -> ProviderRoute | None:
    """Return the first chain provider that exposes a LiteLLM route, if any."""

    for provider in providers:
        if isinstance(provider, LitellmChainProvider):
            litellm_model, api_key, timeout = provider.litellm_route()
            return ProviderRoute(
                litellm_model=litellm_model,
                api_key=api_key,
                timeout_seconds=timeout,
                provider_name=provider.name,
                model=provider.model,
            )
    return None
