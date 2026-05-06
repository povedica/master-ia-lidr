"""Anthropic chain entry routed through LiteLLM (via ai_model_service)."""

from __future__ import annotations

from app.config import Settings
from app.services.ai_model_service import acomplete_chat
from app.services.providers.base import (
    ProviderConfigError,
    ProviderResult,
)


class AnthropicProvider:
    """LLM chain entry targeting Anthropic models via LiteLLM."""

    name = "anthropic"

    def __init__(self, settings: Settings) -> None:
        if not settings.anthropic_api_key:
            raise ProviderConfigError("Anthropic API key is not configured.")
        self._settings = settings
        self.model = settings.anthropic_litellm_model_id()

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
            timeout_seconds=self._settings.anthropic_timeout_seconds,
            chain_provider=self.name,
            api_key=self._settings.anthropic_api_key,
        )
        return ProviderResult(
            text=outcome.text,
            provider=self.name,
            model=outcome.model,
            usage=outcome.usage,
            finish_reason=outcome.finish_reason,
        )
