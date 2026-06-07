"""LLM chain: LiteLLM-backed rows, static fallback, and `build_provider_chain`."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator, Callable

from app.config import Settings
from app.services.ai_model_service import acomplete_chat, astream_chat
from app.services.llm_types import (
    LLMProvider,
    ProviderConfigError,
    ProviderResult,
    UsageInfo,
)

logger = logging.getLogger(__name__)

ProviderFactory = Callable[[Settings], LLMProvider | None]


class LitellmChainProvider:
    """One configured LiteLLM route (e.g. OpenAI or Anthropic credentials)."""

    def __init__(
        self,
        *,
        name: str,
        litellm_model: str,
        api_key: str,
        timeout_seconds: float,
    ) -> None:
        self.name = name
        self.model = litellm_model
        self._api_key = api_key
        self._timeout_seconds = timeout_seconds

    async def complete(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        max_output_tokens: int,
    ) -> ProviderResult:
        outcome = await acomplete_chat(
            litellm_model=self.model,
            system_message=system_prompt,
            user_message=user_prompt,
            max_output_tokens=max_output_tokens,
            timeout_seconds=self._timeout_seconds,
            chain_provider=self.name,
            api_key=self._api_key,
        )
        return ProviderResult(
            text=outcome.text,
            provider=self.name,
            model=outcome.model,
            usage=outcome.usage,
            finish_reason=outcome.finish_reason,
        )

    async def stream_complete(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        max_output_tokens: int,
    ) -> AsyncIterator[str | UsageInfo]:
        """Yield text deltas from the upstream LiteLLM streaming completion."""

        async for delta in astream_chat(
            litellm_model=self.model,
            system_message=system_prompt,
            user_message=user_prompt,
            max_output_tokens=max_output_tokens,
            timeout_seconds=self._timeout_seconds,
            chain_provider=self.name,
            api_key=self._api_key,
        ):
            yield delta

    def litellm_route(self) -> tuple[str, str, float]:
        """LiteLLM model id, API key, and timeout for structured completions outside the chain."""

        return self.model, self._api_key, self._timeout_seconds


_DEGRADED_PREAMBLE = (
    "## Estimation: Temporary degraded mode\n\n"
    "### Assumptions\n"
    "- Live model providers are currently unavailable.\n"
    "- This response is a coarse fallback and should be reviewed manually.\n\n"
)

_TASKS_TABLE = (
    "### Tasks\n"
    "| Task | Hours |\n"
    "|------|------:|\n"
    "| Requirements clarification | 4 |\n"
    "| Technical design draft | 6 |\n"
    "| Implementation + tests | 16 |\n"
    "| QA + deployment checklist | 6 |\n"
    "| **Total** | **32** |\n\n"
)

_DELIVERY_NOTES = (
    "### Delivery notes\n"
    "Re-run the estimate when model providers recover to replace this degraded output."
)

_STANDARD_BUDGET = (
    "## Effort Summary\n"
    "- Base effort: 28 hours\n"
    "- Buffer (~14%): 4 hours\n"
    "- **Total: 32 hours**\n\n"
    "## Budget (indicative)\n"
    "- EUR range (low–high): approximately **1,700–2,400 EUR** (aligned with ~32h and a blended "
    "~55–75 EUR/h placeholder assumption; illustrative only, not a quote)\n"
    "- Uses the same fictional rate-card band (35–100 EUR/h) as live mode when no custom rates are supplied\n\n"
)


def _build_degraded_markdown() -> str:
    return "".join([_DEGRADED_PREAMBLE, _TASKS_TABLE, _STANDARD_BUDGET, _DELIVERY_NOTES])


class StaticFallbackProvider:
    """Deterministic fallback provider used as last resort."""

    name = "static_fallback"
    model = "static-v1"

    async def complete(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        max_output_tokens: int,
    ) -> ProviderResult:
        del system_prompt
        del user_prompt
        del max_output_tokens
        text = _build_degraded_markdown()
        return ProviderResult(
            text=text,
            provider=self.name,
            model=self.model,
            usage=None,
            finish_reason="stop",
        )


def _openai_factory(settings: Settings) -> LLMProvider | None:
    if not settings.openai_api_key:
        logger.info(
            "provider_skipped",
            extra={"provider": "openai", "reason": "missing_api_key"},
        )
        return None
    return LitellmChainProvider(
        name="openai",
        litellm_model=settings.openai_litellm_model_id(),
        api_key=settings.openai_api_key,
        timeout_seconds=settings.openai_timeout_seconds,
    )


def _anthropic_factory(settings: Settings) -> LLMProvider | None:
    if not settings.anthropic_api_key:
        logger.info(
            "provider_skipped",
            extra={"provider": "anthropic", "reason": "missing_api_key"},
        )
        return None
    return LitellmChainProvider(
        name="anthropic",
        litellm_model=settings.anthropic_litellm_model_id(),
        api_key=settings.anthropic_api_key,
        timeout_seconds=settings.anthropic_timeout_seconds,
    )


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
