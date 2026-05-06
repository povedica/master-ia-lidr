"""LiteLLM gateway: the only module that imports LiteLLM for chat completions."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import httpx
import litellm
from litellm import acompletion
from litellm import exceptions as litellm_exc
from openai import APITimeoutError as OpenAIAPITimeoutError

from app.services.llm_types import (
    ProviderConfigError,
    ProviderInvalidResponseError,
    ProviderTimeoutError,
    ProviderUnavailableError,
    UsageInfo,
)

logger = logging.getLogger(__name__)

litellm.suppress_debug_info = True


def _infer_llm_vendor(litellm_model: str) -> str:
    if "/" not in litellm_model:
        return "unknown"
    return litellm_model.split("/", 1)[0]


def _normalize_text_content(raw: Any) -> str:
    """Turn LiteLLM / OpenAI message content into trimmed plain text."""

    if raw is None:
        return ""
    if isinstance(raw, str):
        return raw.strip()
    if isinstance(raw, list):
        parts: list[str] = []
        for block in raw:
            if isinstance(block, dict):
                txt = block.get("text") or block.get("content")
                if isinstance(txt, str) and txt.strip():
                    parts.append(txt.strip())
            else:
                t = getattr(block, "text", None)
                if isinstance(t, str) and t.strip():
                    parts.append(t.strip())
        return "\n".join(parts).strip()
    return str(raw).strip()


def _usage_from_litellm(usage_obj: Any) -> UsageInfo | None:
    if usage_obj is None:
        return None
    pi = int(getattr(usage_obj, "prompt_tokens", 0) or 0)
    co = int(getattr(usage_obj, "completion_tokens", 0) or 0)
    tot_raw = getattr(usage_obj, "total_tokens", None)
    total = int(tot_raw if tot_raw is not None else pi + co)
    prep_in = int(getattr(usage_obj, "preprocessing_input_tokens", 0) or 0)
    prep_out = int(getattr(usage_obj, "preprocessing_output_tokens", 0) or 0)
    return UsageInfo(
        prompt_tokens=pi,
        completion_tokens=co,
        total_tokens=total,
        preprocessing_input_tokens=prep_in,
        preprocessing_output_tokens=prep_out,
    )


def _map_litellm_exception(
    exc: BaseException,
    *,
    litellm_model: str,
    chain_provider: str,
) -> ProviderConfigError | ProviderTimeoutError | ProviderUnavailableError | ProviderInvalidResponseError:
    """Map LiteLLM / HTTP / OpenAI transport errors onto domain provider errors."""

    label = chain_provider.lower()
    if isinstance(exc, (OpenAIAPITimeoutError, httpx.TimeoutException, TimeoutError)):
        if label == "openai":
            return ProviderTimeoutError("OpenAI request timed out.")
        if label == "anthropic":
            return ProviderTimeoutError("Anthropic request timed out.")
        return ProviderTimeoutError("LLM request timed out.")

    if isinstance(exc, litellm_exc.AuthenticationError):
        if label == "openai":
            return ProviderConfigError("OpenAI authentication failed.")
        if label == "anthropic":
            return ProviderConfigError("Anthropic authentication failed.")
        return ProviderConfigError("LLM authentication failed.")

    if isinstance(exc, litellm_exc.NotFoundError):
        if label == "anthropic":
            return ProviderConfigError(
                "Anthropic returned 404 for this model id (retired name, typo, or not enabled for your key). "
                "Set ANTHROPIC_MODEL to a current LiteLLM id (e.g. anthropic/claude-haiku-4-5-20251001) "
                "or a bare Anthropic model name we can prefix.",
            )
        if label == "openai":
            return ProviderConfigError(
                "OpenAI returned an error for this model id (wrong name or access). "
                "Check OPENAI_MODEL or use a prefixed LiteLLM id in OPENAI_MODEL.",
            )
        return ProviderConfigError("The configured LLM model was not found for this route.")

    if isinstance(
        exc,
        (
            litellm_exc.BadRequestError,
            litellm_exc.InvalidRequestError,
            litellm_exc.UnsupportedParamsError,
            litellm_exc.UnprocessableEntityError,
            litellm_exc.PermissionDeniedError,
        ),
    ):
        return ProviderConfigError("LLM rejected the request (configuration or unsupported parameters).")

    if isinstance(exc, litellm_exc.RateLimitError):
        if label == "openai":
            return ProviderUnavailableError("OpenAI rate limit reached.")
        if label == "anthropic":
            return ProviderUnavailableError("Anthropic rate limit reached.")
        return ProviderUnavailableError("LLM rate limit reached.")

    if isinstance(
        exc,
        (
            litellm_exc.APIConnectionError,
            litellm_exc.ServiceUnavailableError,
            litellm_exc.InternalServerError,
            litellm_exc.BadGatewayError,
            litellm_exc.APIError,
            litellm_exc.BudgetExceededError,
            litellm_exc.ContentPolicyViolationError,
            litellm_exc.ContextWindowExceededError,
            litellm_exc.MidStreamFallbackError,
        ),
    ):
        if label == "openai":
            return ProviderUnavailableError("OpenAI returned an API error.")
        if label == "anthropic":
            return ProviderUnavailableError("Anthropic returned an API error.")
        return ProviderUnavailableError("LLM upstream returned an error.")

    return ProviderUnavailableError("Unexpected LLM failure.")


@dataclass(frozen=True)
class LiteLLMChatOutcome:
    """Normalized chat completion extracted from LiteLLM."""

    text: str
    model: str
    usage: UsageInfo | None
    finish_reason: str


async def acomplete_chat(
    *,
    litellm_model: str,
    system_message: str,
    user_message: str,
    max_output_tokens: int,
    timeout_seconds: float,
    chain_provider: str,
    api_key: str | None = None,
) -> LiteLLMChatOutcome:
    """Run a chat completion via LiteLLM asynchronously."""

    trimmed_system = system_message.strip()
    trimmed_user = user_message.strip()
    if not trimmed_user:
        raise ProviderInvalidResponseError("User message content is empty.")

    vendor = _infer_llm_vendor(litellm_model)
    logger.info(
        "llm_request_started",
        extra={
            "event": "llm_request_started",
            "llm_model": litellm_model,
            "llm_vendor": vendor,
            "chain_provider": chain_provider,
        },
    )

    messages: list[dict[str, Any]] = [
        {"role": "system", "content": trimmed_system},
        {"role": "user", "content": trimmed_user},
    ]

    kwargs: dict[str, Any] = {"timeout": timeout_seconds}
    if api_key:
        kwargs["api_key"] = api_key

    try:
        response = await acompletion(
            model=litellm_model,
            messages=messages,
            max_completion_tokens=max_output_tokens,
            **kwargs,
        )
    except Exception as exc:  # noqa: BLE001 — boundary: map upstream failures onto ProviderError subclasses
        mapped = _map_litellm_exception(
            exc, litellm_model=litellm_model, chain_provider=chain_provider
        )
        logger.warning(
            "llm_request_failed",
            extra={
                "event": "llm_request_failed",
                "llm_model": litellm_model,
                "llm_vendor": vendor,
                "chain_provider": chain_provider,
                "error_type": type(exc).__name__,
            },
        )
        raise mapped from exc

    choice = response.choices[0] if getattr(response, "choices", None) else None
    message = getattr(choice, "message", None) if choice else None
    raw_content = getattr(message, "content", "") if message else ""
    content = _normalize_text_content(raw_content)

    finish = getattr(choice, "finish_reason", None) or "stop"
    resolved_model = str(getattr(response, "model", None) or litellm_model)
    usage_info = _usage_from_litellm(getattr(response, "usage", None))

    if not content:
        logger.warning(
            "llm_request_failed",
            extra={
                "event": "llm_request_failed",
                "llm_model": litellm_model,
                "llm_vendor": vendor,
                "chain_provider": chain_provider,
                "error_type": "empty_completion",
            },
        )
        empty_msg = "LLM returned an empty response."
        if chain_provider == "openai":
            empty_msg = "OpenAI returned an empty response."
        elif chain_provider == "anthropic":
            empty_msg = "Anthropic returned an empty response."
        raise ProviderInvalidResponseError(empty_msg)

    logger.info(
        "llm_request_succeeded",
        extra={
            "event": "llm_request_succeeded",
            "llm_model": litellm_model,
            "resolved_model": resolved_model,
            "llm_vendor": vendor,
            "chain_provider": chain_provider,
        },
    )

    return LiteLLMChatOutcome(
        text=content,
        model=resolved_model,
        usage=usage_info,
        finish_reason=str(finish),
    )
