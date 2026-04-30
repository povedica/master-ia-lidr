"""Anthropic provider implementation for estimation generation."""

from __future__ import annotations

from anthropic import (
    APIConnectionError,
    APIError,
    APITimeoutError,
    AsyncAnthropic,
    AuthenticationError,
    RateLimitError,
)

from app.config import Settings
from app.services.providers.base import (
    ProviderConfigError,
    ProviderInvalidResponseError,
    ProviderResult,
    ProviderTimeoutError,
    ProviderUnavailableError,
    UsageInfo,
)


class AnthropicProvider:
    """LLM provider backed by Anthropic messages API."""

    name = "anthropic"

    def __init__(self, settings: Settings) -> None:
        if not settings.anthropic_api_key:
            raise ProviderConfigError("Anthropic API key is not configured.")
        self.model = settings.anthropic_model
        self._client = AsyncAnthropic(
            api_key=settings.anthropic_api_key,
            timeout=settings.anthropic_timeout_seconds,
        )

    async def complete(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        max_output_tokens: int,
    ) -> ProviderResult:
        """Request a completion and normalize Anthropic response."""

        try:
            response = await self._client.messages.create(
                model=self.model,
                max_tokens=max_output_tokens,
                system=system_prompt,
                messages=[{"role": "user", "content": user_prompt}],
            )
        except APITimeoutError as exc:
            raise ProviderTimeoutError("Anthropic request timed out.") from exc
        except (RateLimitError, APIConnectionError) as exc:
            raise ProviderUnavailableError("Anthropic is temporarily unavailable.") from exc
        except AuthenticationError as exc:
            raise ProviderConfigError("Anthropic authentication failed.") from exc
        except APIError as exc:
            raise ProviderUnavailableError("Anthropic returned an API error.") from exc

        text_parts = [block.text for block in response.content if getattr(block, "type", "") == "text"]
        content = "\n".join(part.strip() for part in text_parts if part.strip()).strip()
        if not content:
            raise ProviderInvalidResponseError("Anthropic returned an empty response.")

        usage = getattr(response, "usage", None)
        usage_info = None
        if usage:
            usage_info = UsageInfo(
                prompt_tokens=getattr(usage, "input_tokens", 0),
                completion_tokens=getattr(usage, "output_tokens", 0),
                total_tokens=getattr(usage, "input_tokens", 0) + getattr(usage, "output_tokens", 0),
            )

        return ProviderResult(
            text=content,
            provider=self.name,
            model=self.model,
            usage=usage_info,
        )

