"""Inspectable fake for ``complete_structured`` in integration tests."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TypeVar

from pydantic import BaseModel

from app.schemas.estimation_result import EstimationLineItem, EstimationResult, EstimationTotals
from app.services.llm_types import UsageInfo

TModel = TypeVar("TModel", bound=BaseModel)

_DEFAULT_SUMMARY = "Fixed summary for integration test run."


@dataclass(frozen=True)
class CapturedLLMCall:
    """One structured completion invocation observed by the fake."""

    system_prompt: str
    user_prompt: str
    response_model: type[BaseModel]
    call_index: int
    messages: list[dict[str, str]] | None = None


@dataclass
class FakeStructuredLLM:
    """Records prompts and returns deterministic ``EstimationResult`` instances."""

    calls: list[CapturedLLMCall] = field(default_factory=list)

    def reset(self) -> None:
        self.calls.clear()

    def last_call(self) -> CapturedLLMCall:
        if not self.calls:
            raise AssertionError("FakeStructuredLLM has no recorded calls")
        return self.calls[-1]

    async def complete_structured(
        self,
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
    ) -> tuple[TModel, UsageInfo | None, str | None]:
        del (
            litellm_model,
            chain_provider,
            api_key,
            timeout_seconds,
            max_output_tokens,
            max_attempts,
        )
        index = len(self.calls)
        self.calls.append(
            CapturedLLMCall(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                response_model=response_model,
                call_index=index,
            )
        )
        result = self._dispatch(user_prompt)
        if not issubclass(response_model, EstimationResult):
            raise TypeError(f"Unsupported response_model for fake: {response_model!r}")
        validated = response_model.model_validate(result.model_dump())
        usage = UsageInfo(prompt_tokens=1, completion_tokens=1, total_tokens=2)
        return validated, usage, "stop"

    def _dispatch(self, user_prompt: str) -> EstimationResult:
        if "ATTACH_MARKER:USE_REDIS" in user_prompt:
            return _estimation_result(
                title="Estimate",
                summary=_DEFAULT_SUMMARY,
                line_item_name="Redis (from attachment)",
            )
        if "[[TECH:redis]]" in user_prompt:
            return _estimation_result(
                title="Estimate",
                summary=_DEFAULT_SUMMARY,
                line_item_name="Redis integration",
            )
        return _estimation_result(title="Estimate", summary=_DEFAULT_SUMMARY)


def _estimation_result(
    *,
    title: str,
    summary: str,
    line_item_name: str = "Default task",
) -> EstimationResult:
    line = EstimationLineItem(name=line_item_name, hours=1.0, cost_eur=50.0)
    totals = EstimationTotals(hours=1.0, cost_eur=50.0)
    return EstimationResult(
        title=title,
        summary=summary,
        phases=[],
        line_items=[line],
        totals=totals,
        duration_weeks=1.0,
        confidence=0.85,
    )
