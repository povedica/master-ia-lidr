"""Anthropic provider implementation for estimation generation."""

from __future__ import annotations

import logging

from anthropic import (
    APIConnectionError,
    APIError,
    APITimeoutError,
    AsyncAnthropic,
    AuthenticationError,
    NotFoundError,
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

logger = logging.getLogger(__name__)


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
        except NotFoundError as exc:
            logger.warning(
                "anthropic_model_not_found",
                extra={"model": self.model, "error_type": type(exc).__name__},
            )
            raise ProviderConfigError(
                "Anthropic returned 404 for this model id (retired name, typo, or not enabled for your key). "
                "Set ANTHROPIC_MODEL to a current id, e.g. claude-haiku-4-5-20251001 or claude-3-haiku-20240307. "
                "See https://docs.anthropic.com/en/api/models"
            ) from exc
        except APIError as exc:
            status = getattr(exc, "status_code", None)
            logger.warning(
                "anthropic_api_error",
                extra={
                    "model": self.model,
                    "error_type": type(exc).__name__,
                    "status_code": status,
                },
            )
            raise ProviderUnavailableError("Anthropic returned an API error.") from exc

        text_parts = [block.text for block in response.content if getattr(block, "type", "") == "text"]
        content = "\n".join(part.strip() for part in text_parts if part.strip()).strip()
        if not content:
            raise ProviderInvalidResponseError("Anthropic returned an empty response.")

        stop_reason = getattr(response, "stop_reason", None) or "end_turn"

        usage = getattr(response, "usage", None)
        usage_info = None
        if usage:
            prep_in = int(getattr(usage, "preprocessing_input_tokens", 0) or 0)
            prep_out = int(getattr(usage, "preprocessing_output_tokens", 0) or 0)
            usage_info = UsageInfo(
                prompt_tokens=getattr(usage, "input_tokens", 0),
                completion_tokens=getattr(usage, "output_tokens", 0),
                total_tokens=getattr(usage, "input_tokens", 0) + getattr(usage, "output_tokens", 0),
                preprocessing_input_tokens=prep_in,
                preprocessing_output_tokens=prep_out,
            )

        return ProviderResult(
            text=content,
            provider=self.name,
            model=self.model,
            usage=usage_info,
            finish_reason=str(stop_reason),
        )

