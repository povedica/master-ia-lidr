"""Provider registry and chain builder utilities."""

from __future__ import annotations

import logging
from collections.abc import Callable

from app.config import Settings
from app.services.providers.base import LLMProvider, ProviderConfigError
from app.services.providers.anthropic_provider import AnthropicProvider
from app.services.providers.openai_provider import OpenAIProvider
from app.services.providers.static_fallback import StaticFallbackProvider

logger = logging.getLogger(__name__)

ProviderFactory = Callable[[Settings], LLMProvider | None]


def _openai_factory(settings: Settings) -> LLMProvider | None:
    if not settings.openai_api_key:
        logger.info(
            "provider_skipped",
            extra={"provider": "openai", "reason": "missing_api_key"},
        )
        return None
    return OpenAIProvider(settings)


def _anthropic_factory(settings: Settings) -> LLMProvider | None:
    if not settings.anthropic_api_key:
        logger.info(
            "provider_skipped",
            extra={"provider": "anthropic", "reason": "missing_api_key"},
        )
        return None
    return AnthropicProvider(settings)


PROVIDER_REGISTRY: dict[str, ProviderFactory] = {
    "openai": _openai_factory,
    "anthropic": _anthropic_factory,
}


def _parse_provider_names(raw_value: str) -> list[str]:
    return [name.strip().lower() for name in raw_value.split(",") if name.strip()]


def build_provider_chain(settings: Settings) -> list[LLMProvider]:
    """Build the ordered provider chain from settings."""

    chain: list[LLMProvider] = []
    for provider_name in _parse_provider_names(settings.llm_providers):
        factory = PROVIDER_REGISTRY.get(provider_name)
        if factory is None:
            logger.warning("provider_unknown", extra={"provider": provider_name})
            continue

        try:
            provider = factory(settings)
        except ProviderConfigError:
            raise

        if provider is not None:
            chain.append(provider)

    if settings.static_fallback_enabled:
        chain.append(StaticFallbackProvider())

    if not chain:
        raise ProviderConfigError(
            "No provider could be configured from LLM_PROVIDERS and static fallback is disabled.",
        )
    return chain

