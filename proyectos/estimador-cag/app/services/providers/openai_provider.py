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

    async def complete(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        max_output_tokens: int,
    ) -> ProviderResult:
        """Request a completion and map SDK exceptions into provider errors."""

        try:
            response = await self._client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                max_completion_tokens=max_output_tokens,
            )
        except APITimeoutError as exc:
            raise ProviderTimeoutError("OpenAI request timed out.") from exc
        except RateLimitError as exc:
            raise ProviderUnavailableError("OpenAI rate limit reached.") from exc
        except AuthenticationError as exc:
            raise ProviderConfigError("OpenAI authentication failed.") from exc
        except APIError as exc:
            raise ProviderUnavailableError("OpenAI returned an API error.") from exc

        choice = response.choices[0] if response.choices else None
        message = choice.message if choice else None
        content = (message.content or "").strip() if message else ""
        if not content:
            raise ProviderInvalidResponseError("OpenAI returned an empty response.")

        finish = (choice.finish_reason or "stop") if choice else "stop"

        usage = response.usage
        usage_info = None
        if usage:
            prep_in = int(getattr(usage, "preprocessing_input_tokens", 0) or 0)
            prep_out = int(getattr(usage, "preprocessing_output_tokens", 0) or 0)
            usage_info = UsageInfo(
                prompt_tokens=usage.prompt_tokens,
                completion_tokens=usage.completion_tokens,
                total_tokens=usage.total_tokens,
                preprocessing_input_tokens=prep_in,
                preprocessing_output_tokens=prep_out,
            )

        return ProviderResult(
            text=content,
            provider=self.name,
            model=self.model,
            usage=usage_info,
            finish_reason=str(finish),
        )
