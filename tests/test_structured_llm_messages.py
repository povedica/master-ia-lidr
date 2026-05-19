"""Tests for multi-message structured completion."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.schemas.estimation_result import EstimationLineItem, EstimationResult, EstimationTotals
from app.services.structured_llm_client import (
    StructuredCompletionError,
    complete_structured,
)


def _sample_domain() -> EstimationResult:
    li = EstimationLineItem(name="A", hours=1.0, cost_eur=50.0)
    totals = EstimationTotals(hours=1.0, cost_eur=50.0)
    return EstimationResult(
        title="Title",
        summary="Summary for structured messages test",
        phases=[],
        line_items=[li],
        totals=totals,
        duration_weeks=1.0,
        confidence=0.9,
    )


@pytest.mark.asyncio
async def test_complete_structured_uses_messages_override_when_provided() -> None:
    expected = _sample_domain()
    captured: list[list[dict[str, str]]] = []

    async def fake_create_with_completion(
        messages: list[dict[str, str]],
        response_model: type[EstimationResult],
        **kwargs: object,
    ) -> tuple[EstimationResult, object]:
        del response_model, kwargs
        captured.append(messages)
        return expected, object()

    fake_client = AsyncMock()
    fake_client.chat.completions.create_with_completion = fake_create_with_completion

    override = [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "prior"},
        {"role": "assistant", "content": "prior reply"},
        {"role": "user", "content": "current"},
    ]

    with patch("app.services.structured_llm_client.instructor") as mock_inst:
        mock_inst.from_litellm.return_value = fake_client
        await complete_structured(
            litellm_model="openai/gpt-4o-mini",
            chain_provider="openai",
            api_key="sk-test",
            timeout_seconds=5.0,
            system_prompt="ignored",
            user_prompt="ignored",
            max_output_tokens=800,
            response_model=EstimationResult,
            max_attempts=1,
            messages=override,
        )

    assert captured == [override]


@pytest.mark.asyncio
async def test_complete_structured_rejects_invalid_messages_override() -> None:
    with pytest.raises(StructuredCompletionError, match="messages"):
        await complete_structured(
            litellm_model="openai/gpt-4o-mini",
            chain_provider="openai",
            api_key="sk-test",
            timeout_seconds=5.0,
            system_prompt="sys",
            user_prompt="user",
            max_output_tokens=800,
            response_model=EstimationResult,
            max_attempts=1,
            messages=[
                {"role": "user", "content": "missing system"},
            ],
        )
