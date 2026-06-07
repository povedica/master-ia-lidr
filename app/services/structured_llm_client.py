"""Typed structured completion via Instructor + LiteLLM (async)."""

from __future__ import annotations

import logging
from typing import TypeVar

import instructor
from litellm import acompletion
from pydantic import BaseModel, ValidationError

from app.services.llm_call_persistence import build_llm_call_record, maybe_persist_llm_call, sanitize_request_kwargs, usage_to_dict
from app.services.llm_types import UsageInfo
from app.services.observability.bootstrap import get_observability
from app.services.observability.llm_instrumentation import (
    STRUCTURED_LLM_GENERATION_NAME,
    complete_llm_generation,
    generation_metadata_for_litellm,
    infer_llm_vendor,
)

logger = logging.getLogger(__name__)

TModel = TypeVar("TModel", bound=BaseModel)


class StructuredCompletionError(RuntimeError):
    """Raised when structured output cannot be produced after retries."""


def _validate_messages_for_structured_completion(messages: list[dict[str, str]]) -> None:
    if not messages:
        raise StructuredCompletionError("messages must not be empty")
    if messages[0].get("role") != "system":
        raise StructuredCompletionError("messages must start with a system role")
    if messages[-1].get("role") != "user":
        raise StructuredCompletionError("messages must end with a user role")
    prior = messages[1:-1]
    if len(prior) % 2 != 0:
        raise StructuredCompletionError("messages prior pairs must be user/assistant pairs")
    for index, message in enumerate(prior):
        expected = "user" if index % 2 == 0 else "assistant"
        if message.get("role") != expected:
            raise StructuredCompletionError("messages roles must alternate user/assistant after system")


def _resolve_completion_messages(
    *,
    system_prompt: str,
    user_prompt: str,
    messages: list[dict[str, str]] | None,
) -> list[dict[str, str]]:
    if messages is None:
        return [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
    _validate_messages_for_structured_completion(messages)
    return messages


def _usage_from_raw(raw: object | None) -> UsageInfo | None:
    if raw is None:
        return None
    usage_obj = getattr(raw, "usage", None)
    if usage_obj is None:
        return None
    pi = int(getattr(usage_obj, "prompt_tokens", 0) or 0)
    co = int(getattr(usage_obj, "completion_tokens", 0) or 0)
    tot_raw = getattr(usage_obj, "total_tokens", None)
    total = int(tot_raw if tot_raw is not None else pi + co)
    return UsageInfo(
        prompt_tokens=pi,
        completion_tokens=co,
        total_tokens=total,
        preprocessing_input_tokens=0,
        preprocessing_output_tokens=0,
    )


def _resolved_model(raw_completion: object | None, litellm_model: str) -> str:
    if raw_completion is not None:
        model = getattr(raw_completion, "model", None)
        if model:
            return str(model)
    return litellm_model


async def complete_structured(
    *,
    litellm_model: str,
    chain_provider: str,
    api_key: str,
    timeout_seconds: float,
    system_prompt: str,
    user_prompt: str,
    max_output_tokens: int,
    response_model: type[TModel],
    max_attempts: int,
    messages: list[dict[str, str]] | None = None,
) -> tuple[TModel, UsageInfo | None, str | None]:
    """Return a validated Pydantic instance, optional usage, and finish_reason."""

    completion_messages = _resolve_completion_messages(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        messages=messages,
    )

    request_snapshot = {
        "litellm_model": litellm_model,
        "chain_provider": chain_provider,
        "messages": completion_messages,
        "max_output_tokens": max_output_tokens,
        "timeout_seconds": timeout_seconds,
        "response_model": response_model.__name__,
        "extra_kwargs": sanitize_request_kwargs(
            {
                "api_key": api_key,
                "timeout": timeout_seconds,
                "max_tokens": max_output_tokens,
            }
        ),
    }

    # Do not pass max_retries here: Instructor forwards it into LiteLLM's ``acompletion``,
    # which then collides with Instructor's own kwargs (``TypeError: multiple values for max_retries``).
    client = instructor.from_litellm(acompletion)
    observability = get_observability()
    vendor = infer_llm_vendor(litellm_model)
    last_exc: BaseException | None = None
    for attempt in range(max(1, max_attempts)):
        with observability.start_generation(
            STRUCTURED_LLM_GENERATION_NAME,
            model=litellm_model,
            metadata={
                **generation_metadata_for_litellm(
                    chain_provider=chain_provider,
                    litellm_model=litellm_model,
                    llm_vendor=vendor,
                ),
                "attempt": str(attempt + 1),
                "max_attempts": str(max_attempts),
            },
        ):
            try:
                parsed, raw_completion = await client.chat.completions.create_with_completion(
                    completion_messages,
                    response_model=response_model,
                    model=litellm_model,
                    max_tokens=max_output_tokens,
                    api_key=api_key,
                    timeout=timeout_seconds,
                )
            except ValidationError as exc:
                observability.record_error(exc)
                last_exc = exc
                logger.warning(
                    "structured_output_validation_failed",
                    extra={
                        "attempt": attempt + 1,
                        "max_attempts": max_attempts,
                        "error_type": type(exc).__name__,
                    },
                )
                continue
            except Exception as exc:  # noqa: BLE001 — map last failure for operator visibility
                observability.record_error(exc)
                last_exc = exc
                logger.warning(
                    "structured_output_call_failed",
                    extra={
                        "attempt": attempt + 1,
                        "max_attempts": max_attempts,
                        "error_type": type(exc).__name__,
                    },
                )
                continue

            usage = _usage_from_raw(raw_completion)
            finish = None
            if raw_completion is not None and hasattr(raw_completion, "choices") and raw_completion.choices:
                ch0 = raw_completion.choices[0]
                fr = getattr(ch0, "finish_reason", None)
                if isinstance(fr, str):
                    finish = fr
            resolved_model = _resolved_model(raw_completion, litellm_model)
            complete_llm_generation(
                observability,
                resolved_model=resolved_model,
                usage=usage,
                finish_reason=finish or "stop",
                output_text=parsed.model_dump_json(),
            )
            maybe_persist_llm_call(
                build_llm_call_record(
                    call_kind="structured",
                    model_request=request_snapshot,
                    response={
                        "structured_output": parsed.model_dump(mode="json"),
                        "resolved_model": resolved_model,
                        "finish_reason": finish or "stop",
                        "usage": usage_to_dict(usage),
                    },
                )
            )
            return parsed, usage, finish

    raise StructuredCompletionError(
        "The model did not return a response matching the required schema."
    ) from last_exc
