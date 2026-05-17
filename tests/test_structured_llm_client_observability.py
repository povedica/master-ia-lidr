"""Observability on structured Instructor completions."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.schemas.estimation_result import EstimationLineItem, EstimationResult, EstimationTotals
from app.services.structured_llm_client import complete_structured


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
async def test_complete_structured_records_generation_with_usage() -> None:
    expected = _sample_domain()
    usage_obj = SimpleNamespace(
        prompt_tokens=100,
        completion_tokens=50,
        total_tokens=150,
    )
    raw_completion = SimpleNamespace(model="openai/gpt-4o-mini", usage=usage_obj, choices=[])

    async def fake_create_with_completion(
        messages: object,
        response_model: type[EstimationResult],
        **kwargs: object,
    ) -> tuple[EstimationResult, object]:
        del messages, kwargs
        return expected, raw_completion

    fake_client = AsyncMock()
    fake_client.chat.completions.create_with_completion = fake_create_with_completion

    obs = MagicMock()
    generation_cm = MagicMock()
    generation_cm.__enter__ = MagicMock(return_value=None)
    generation_cm.__exit__ = MagicMock(return_value=False)
    obs.start_generation.return_value = generation_cm

    with (
        patch("app.services.structured_llm_client.instructor") as mock_inst,
        patch("app.services.structured_llm_client.get_observability", return_value=obs),
    ):
        mock_inst.from_litellm.return_value = fake_client
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
        )

    obs.start_generation.assert_called_once()
    assert obs.start_generation.call_args.args[0] == "estimator.llm.structured_output"
    assert obs.start_generation.call_args.kwargs["model"] == "openai/gpt-4o-mini"

    obs.update_generation_usage.assert_called_once()
    usage_arg = obs.update_generation_usage.call_args.args[0]
    assert usage_arg["prompt_tokens"] == 100
    assert usage_arg["completion_tokens"] == 50

    meta = obs.update_generation_metadata.call_args.kwargs["metadata"]
    assert meta["resolved_model"] == "openai/gpt-4o-mini"
    assert meta["finish_reason"] == "stop"
