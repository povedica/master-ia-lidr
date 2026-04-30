"""OpenAI provider implementation for estimation generation."""

from __future__ import annotations

from openai import APIError, APITimeoutError, AsyncOpenAI, AuthenticationError, RateLimitError

from app.config import Settings
from app.services.providers.base import (
    ProviderConfigError,
    ProviderInvalidResponseError,
    ProviderResult,
    ProviderTimeoutError,
    ProviderUnavailableError,
    UsageInfo,
)


class OpenAIProvider:
    """LLM provider backed by OpenAI chat completions."""

    name = "openai"

    def __init__(self, settings: Settings) -> None:
        if not settings.openai_api_key:
            raise ProviderConfigError("OpenAI API key is not configured.")
        self.model = settings.openai_model
        self._client = AsyncOpenAI(
            api_key=settings.openai_api_key,
            timeout=settings.openai_timeout_seconds,
        )

    async def complete(self, system_prompt: str, user_prompt: str) -> ProviderResult:
        """Request a completion and map SDK exceptions into provider errors."""

        try:
            response = await self._client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
            )
        except APITimeoutError as exc:
            raise ProviderTimeoutError("OpenAI request timed out.") from exc
        except RateLimitError as exc:
            raise ProviderUnavailableError("OpenAI rate limit reached.") from exc
        except AuthenticationError as exc:
            raise ProviderConfigError("OpenAI authentication failed.") from exc
        except APIError as exc:
            raise ProviderUnavailableError("OpenAI returned an API error.") from exc

        choice = response.choices[0].message if response.choices else None
        content = (choice.content or "").strip() if choice else ""
        if not content:
            raise ProviderInvalidResponseError("OpenAI returned an empty response.")

        usage = response.usage
        usage_info = None
        if usage:
            usage_info = UsageInfo(
                prompt_tokens=usage.prompt_tokens,
                completion_tokens=usage.completion_tokens,
                total_tokens=usage.total_tokens,
            )

        return ProviderResult(
            text=content,
            provider=self.name,
            model=self.model,
            usage=usage_info,
        )
