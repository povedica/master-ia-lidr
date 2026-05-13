"""Typed structured completion via Instructor + LiteLLM (async)."""

from __future__ import annotations

import logging
from typing import TypeVar

import instructor
from litellm import acompletion
from pydantic import BaseModel, ValidationError

from app.services.llm_types import UsageInfo

logger = logging.getLogger(__name__)

TModel = TypeVar("TModel", bound=BaseModel)


class StructuredCompletionError(RuntimeError):
    """Raised when structured output cannot be produced after retries."""


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


async def complete_structured(
    *,
    litellm_model: str,
    api_key: str,
    timeout_seconds: float,
    system_prompt: str,
    user_prompt: str,
    max_output_tokens: int,
    response_model: type[TModel],
    max_attempts: int,
) -> tuple[TModel, UsageInfo | None, str | None]:
    """Return a validated Pydantic instance, optional usage, and finish_reason."""

    # Do not pass max_retries here: Instructor forwards it into LiteLLM's ``acompletion``,
    # which then collides with Instructor's own kwargs (``TypeError: multiple values for max_retries``).
    client = instructor.from_litellm(acompletion)
    last_exc: BaseException | None = None
    for attempt in range(max(1, max_attempts)):
        try:
            parsed, raw_completion = await client.chat.completions.create_with_completion(
                [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                response_model=response_model,
                model=litellm_model,
                max_tokens=max_output_tokens,
                api_key=api_key,
                timeout=timeout_seconds,
            )
            usage = _usage_from_raw(raw_completion)
            finish = None
            if raw_completion is not None and hasattr(raw_completion, "choices") and raw_completion.choices:
                ch0 = raw_completion.choices[0]
                fr = getattr(ch0, "finish_reason", None)
                if isinstance(fr, str):
                    finish = fr
            return parsed, usage, finish
        except ValidationError as exc:
            last_exc = exc
            logger.warning(
                "structured_output_validation_failed",
                extra={
                    "attempt": attempt + 1,
                    "max_attempts": max_attempts,
                    "error_type": type(exc).__name__,
                },
            )
        except Exception as exc:  # noqa: BLE001 — map last failure for operator visibility
            last_exc = exc
            logger.warning(
                "structured_output_call_failed",
                extra={
                    "attempt": attempt + 1,
                    "max_attempts": max_attempts,
                    "error_type": type(exc).__name__,
                },
            )

    raise StructuredCompletionError(
        "The model did not return a response matching the required schema."
    ) from last_exc
