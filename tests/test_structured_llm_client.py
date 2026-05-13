"""Structured LLM client (mocked Instructor path)."""

from unittest.mock import AsyncMock, patch

import pytest

from app.schemas.estimation_result import EstimationLineItem, EstimationResult, EstimationTotals
from app.services.structured_llm_client import StructuredCompletionError, complete_structured


def _sample_domain() -> EstimationResult:
    li = EstimationLineItem(name="A", hours=4.0, cost_eur=200.0)
    totals = EstimationTotals(hours=4.0, cost_eur=200.0)
    return EstimationResult(
        title="Title for structured client test",
        summary="X" * 22,
        phases=[],
        line_items=[li],
        totals=totals,
        duration_weeks=1.0,
        confidence=0.9,
    )


@pytest.mark.asyncio
async def test_complete_structured_returns_validated_model() -> None:
    expected = _sample_domain()

    async def fake_create_with_completion(
        messages: object,
        response_model: type[EstimationResult],
        **kwargs: object,
    ) -> tuple[EstimationResult, object]:
        del messages, kwargs
        return expected, object()

    fake_client = AsyncMock()
    fake_client.chat.completions.create_with_completion = fake_create_with_completion

    with patch("app.services.structured_llm_client.instructor") as mock_inst:
        mock_inst.from_litellm.return_value = fake_client
        got, usage, finish = await complete_structured(
            litellm_model="openai/gpt-4o-mini",
            api_key="sk-test",
            timeout_seconds=5.0,
            system_prompt="sys",
            user_prompt="user",
            max_output_tokens=800,
            response_model=EstimationResult,
            max_attempts=2,
        )
    assert got.title == expected.title
    assert finish is None


@pytest.mark.asyncio
async def test_complete_structured_raises_after_retries() -> None:
    async def always_fail(
        messages: object,
        response_model: type[EstimationResult],
        **kwargs: object,
    ) -> tuple[EstimationResult, object]:
        del messages, response_model, kwargs
        raise ValueError("simulated provider failure")

    fake_client = AsyncMock()
    fake_client.chat.completions.create_with_completion = always_fail

    with patch("app.services.structured_llm_client.instructor") as mock_inst:
        mock_inst.from_litellm.return_value = fake_client
        with pytest.raises(StructuredCompletionError):
            await complete_structured(
                litellm_model="openai/gpt-4o-mini",
                api_key="sk-test",
                timeout_seconds=5.0,
                system_prompt="sys",
                user_prompt="user",
                max_output_tokens=800,
                response_model=EstimationResult,
                max_attempts=2,
            )
