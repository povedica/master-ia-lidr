"""LiteLLM gateway: the only module that imports LiteLLM for chat completions."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
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
from app.services.observability.bootstrap import get_observability
from app.services.observability.llm_instrumentation import (
    LLM_GENERATION_NAME,
    complete_llm_generation,
    generation_metadata_for_litellm,
    infer_llm_vendor,
)

logger = logging.getLogger(__name__)

litellm.suppress_debug_info = True


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

    vendor = infer_llm_vendor(litellm_model)
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

    observability = get_observability()
    with observability.start_generation(
        LLM_GENERATION_NAME,
        model=litellm_model,
        metadata=generation_metadata_for_litellm(
            chain_provider=chain_provider,
            litellm_model=litellm_model,
            llm_vendor=vendor,
        ),
    ):
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
            observability.record_error(mapped)
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
            empty_err = ProviderInvalidResponseError(_empty_completion_message(chain_provider))
            observability.record_error(empty_err)
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
            raise empty_err

        complete_llm_generation(
            observability,
            resolved_model=resolved_model,
            usage=usage_info,
            finish_reason=str(finish),
            output_text=content,
        )

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


def _empty_completion_message(chain_provider: str) -> str:
    """Return a provider-aware safe message when the upstream model emits nothing."""

    if chain_provider == "openai":
        return "OpenAI returned an empty response."
    if chain_provider == "anthropic":
        return "Anthropic returned an empty response."
    return "LLM returned an empty response."


def _extract_stream_delta_text(chunk: Any) -> str:
    """Read the textual delta from a LiteLLM streaming chunk (preserves whitespace)."""

    choices = getattr(chunk, "choices", None)
    if not choices:
        return ""
    first = choices[0]
    delta = getattr(first, "delta", None)
    if delta is None:
        # Some LiteLLM emitters expose dict-shaped deltas.
        delta = first.get("delta") if isinstance(first, dict) else None
    if delta is None:
        return ""
    raw = getattr(delta, "content", None)
    if raw is None and isinstance(delta, dict):
        raw = delta.get("content")
    if raw is None:
        return ""
    if isinstance(raw, str):
        return raw
    if isinstance(raw, list):
        parts: list[str] = []
        for block in raw:
            if isinstance(block, dict):
                txt = block.get("text") or block.get("content")
                if isinstance(txt, str):
                    parts.append(txt)
            else:
                txt = getattr(block, "text", None)
                if isinstance(txt, str):
                    parts.append(txt)
        return "".join(parts)
    return str(raw)


async def astream_chat(
    *,
    litellm_model: str,
    system_message: str,
    user_message: str,
    max_output_tokens: int,
    timeout_seconds: float,
    chain_provider: str,
    api_key: str | None = None,
) -> AsyncIterator[str | UsageInfo]:
    """Yield text deltas from a LiteLLM streaming chat completion.

    When the upstream exposes token usage (for example OpenAI with
    ``stream_options.include_usage``), a final :class:`UsageInfo` may be yielded
    after all text deltas.

    Mid-stream upstream failures are mapped onto the same `ProviderError` subclasses
    used by `acomplete_chat`, so callers can apply identical fallback logic.
    """

    trimmed_system = system_message.strip()
    trimmed_user = user_message.strip()
    if not trimmed_user:
        raise ProviderInvalidResponseError("User message content is empty.")

    vendor = infer_llm_vendor(litellm_model)
    logger.info(
        "llm_stream_started",
        extra={
            "event": "llm_stream_started",
            "llm_model": litellm_model,
            "llm_vendor": vendor,
            "chain_provider": chain_provider,
        },
    )

    messages: list[dict[str, Any]] = [
        {"role": "system", "content": trimmed_system},
        {"role": "user", "content": trimmed_user},
    ]

    kwargs: dict[str, Any] = {"timeout": timeout_seconds, "stream": True}
    if api_key:
        kwargs["api_key"] = api_key
    if infer_llm_vendor(litellm_model) == "openai":
        kwargs["stream_options"] = {"include_usage": True}

    observability = get_observability()
    with observability.start_generation(
        LLM_GENERATION_NAME,
        model=litellm_model,
        metadata=generation_metadata_for_litellm(
            chain_provider=chain_provider,
            litellm_model=litellm_model,
            llm_vendor=vendor,
        ),
    ):
        try:
            response_stream = await acompletion(
                model=litellm_model,
                messages=messages,
                max_completion_tokens=max_output_tokens,
                **kwargs,
            )
        except Exception as exc:  # noqa: BLE001 — boundary: map LiteLLM/transport errors to ProviderError
            mapped = _map_litellm_exception(
                exc, litellm_model=litellm_model, chain_provider=chain_provider
            )
            observability.record_error(mapped)
            logger.warning(
                "llm_stream_failed",
                extra={
                    "event": "llm_stream_failed",
                    "llm_model": litellm_model,
                    "llm_vendor": vendor,
                    "chain_provider": chain_provider,
                    "error_type": type(exc).__name__,
                    "phase": "open",
                },
            )
            raise mapped from exc

        emitted_any = False
        last_usage: UsageInfo | None = None
        text_parts: list[str] = []
        try:
            async for chunk in response_stream:
                usage_candidate = _usage_from_litellm(getattr(chunk, "usage", None))
                if usage_candidate is not None:
                    last_usage = usage_candidate
                delta_text = _extract_stream_delta_text(chunk)
                if delta_text:
                    emitted_any = True
                    text_parts.append(delta_text)
                    yield delta_text
        except Exception as exc:  # noqa: BLE001 — boundary: mid-stream upstream failure
            mapped = _map_litellm_exception(
                exc, litellm_model=litellm_model, chain_provider=chain_provider
            )
            observability.record_error(mapped)
            logger.warning(
                "llm_stream_failed",
                extra={
                    "event": "llm_stream_failed",
                    "llm_model": litellm_model,
                    "llm_vendor": vendor,
                    "chain_provider": chain_provider,
                    "error_type": type(exc).__name__,
                    "phase": "iterate",
                },
            )
            raise mapped from exc

        if not emitted_any:
            empty_err = ProviderInvalidResponseError(_empty_completion_message(chain_provider))
            observability.record_error(empty_err)
            logger.warning(
                "llm_stream_failed",
                extra={
                    "event": "llm_stream_failed",
                    "llm_model": litellm_model,
                    "llm_vendor": vendor,
                    "chain_provider": chain_provider,
                    "error_type": "empty_completion",
                    "phase": "iterate",
                },
            )
            raise empty_err

        complete_llm_generation(
            observability,
            resolved_model=litellm_model,
            usage=last_usage,
            finish_reason="stop",
            output_text="".join(text_parts),
        )

    logger.info(
        "llm_stream_succeeded",
        extra={
            "event": "llm_stream_succeeded",
            "llm_model": litellm_model,
            "llm_vendor": vendor,
            "chain_provider": chain_provider,
            "usage_reported": last_usage is not None,
        },
    )
    if last_usage is not None:
        yield last_usage
