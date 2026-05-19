"""Unit tests for the structured LLM fake."""

from __future__ import annotations

import pytest

from app.schemas.estimation_result import EstimationResult
from tests.fakes.fake_llm_provider import FakeStructuredLLM


@pytest.mark.asyncio
async def test_fake_records_complete_structured_calls() -> None:
    fake = FakeStructuredLLM()
    result, usage, finish = await fake.complete_structured(
        litellm_model="openai/gpt-4o-mini",
        chain_provider="openai",
        api_key="test-key",
        timeout_seconds=30.0,
        system_prompt="system",
        user_prompt="user transcript",
        max_output_tokens=800,
        response_model=EstimationResult,
        max_attempts=1,
    )

    assert finish == "stop"
    assert usage is not None
    assert result.title == "Estimate"
    assert len(fake.calls) == 1
    assert fake.last_call().system_prompt == "system"
    assert fake.last_call().user_prompt == "user transcript"


@pytest.mark.asyncio
async def test_fake_dispatch_attachment_marker() -> None:
    fake = FakeStructuredLLM()
    result, _, _ = await fake.complete_structured(
        litellm_model="openai/gpt-4o-mini",
        chain_provider="openai",
        api_key="test-key",
        timeout_seconds=30.0,
        system_prompt="sys",
        user_prompt="see ATTACH_MARKER:USE_REDIS in addendum",
        max_output_tokens=800,
        response_model=EstimationResult,
        max_attempts=1,
    )

    assert result.line_items[0].name == "Redis (from attachment)"
