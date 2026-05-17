"""Observability hooks on the LiteLLM gateway."""

from __future__ import annotations

from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import MagicMock, AsyncMock, patch

import pytest

from app.services.ai_model_service import acomplete_chat
from app.services.llm_types import UsageInfo


def _mock_completion_response(
    *,
    content: str = "hello",
    model: str = "openai/gpt-4o-mini",
) -> SimpleNamespace:
    usage = SimpleNamespace(
        prompt_tokens=10,
        completion_tokens=5,
        total_tokens=15,
        preprocessing_input_tokens=0,
        preprocessing_output_tokens=0,
    )
    message = SimpleNamespace(content=content)
    choice = SimpleNamespace(message=message, finish_reason="stop")
    return SimpleNamespace(choices=[choice], model=model, usage=usage)


@pytest.mark.asyncio
async def test_acomplete_chat_records_generation_when_observability_enabled() -> None:
    obs = MagicMock()
    generation_cm = MagicMock()
    generation_cm.__enter__ = MagicMock(return_value=None)
    generation_cm.__exit__ = MagicMock(return_value=False)
    obs.start_generation.return_value = generation_cm

    async def _fake_completion(**_: object) -> object:
        return _mock_completion_response()

    with (
        patch("app.services.ai_model_service.acompletion", AsyncMock(side_effect=_fake_completion)),
        patch("app.services.ai_model_service.get_observability", return_value=obs),
    ):
        await acomplete_chat(
            litellm_model="openai/gpt-4o-mini",
            system_message="sys",
            user_message="usr",
            max_output_tokens=256,
            timeout_seconds=12.0,
            chain_provider="openai",
        )

    obs.start_generation.assert_called_once()
    call_kwargs = obs.start_generation.call_args.kwargs
    assert call_kwargs["model"] == "openai/gpt-4o-mini"
    assert call_kwargs["metadata"]["provider"] == "openai"
    assert call_kwargs["metadata"]["llm_vendor"] == "openai"

    obs.update_generation_usage.assert_called_once()
    usage_arg = obs.update_generation_usage.call_args.args[0]
    assert usage_arg["prompt_tokens"] == 10
    assert usage_arg["completion_tokens"] == 5

    obs.update_generation_output.assert_called_once_with("hello")
    obs.update_generation_metadata.assert_called_once()
    meta = obs.update_generation_metadata.call_args.kwargs["metadata"]
    assert meta["finish_reason"] == "stop"
    assert meta["resolved_model"] == "openai/gpt-4o-mini"


@pytest.mark.asyncio
async def test_acomplete_chat_records_generation_for_anthropic_route() -> None:
    obs = MagicMock()
    generation_cm = MagicMock()
    generation_cm.__enter__ = MagicMock(return_value=None)
    generation_cm.__exit__ = MagicMock(return_value=False)
    obs.start_generation.return_value = generation_cm

    async def _fake_completion(**_: object) -> object:
        return _mock_completion_response(model="anthropic/claude-haiku-4-5-20251001")

    with (
        patch("app.services.ai_model_service.acompletion", AsyncMock(side_effect=_fake_completion)),
        patch("app.services.ai_model_service.get_observability", return_value=obs),
    ):
        await acomplete_chat(
            litellm_model="anthropic/claude-haiku-4-5-20251001",
            system_message="sys",
            user_message="usr",
            max_output_tokens=128,
            timeout_seconds=10.0,
            chain_provider="anthropic",
        )

    assert obs.start_generation.call_args.kwargs["metadata"]["provider"] == "anthropic"
    assert obs.start_generation.call_args.kwargs["metadata"]["llm_vendor"] == "anthropic"


@pytest.mark.asyncio
async def test_acomplete_chat_records_error_on_provider_failure() -> None:
    obs = MagicMock()
    generation_cm = MagicMock()
    generation_cm.__enter__ = MagicMock(return_value=None)
    generation_cm.__exit__ = MagicMock(return_value=False)
    obs.start_generation.return_value = generation_cm

    from litellm import exceptions as litellm_exc

    err = litellm_exc.AuthenticationError("no", llm_provider="openai", model="openai/x")

    with (
        patch("app.services.ai_model_service.acompletion", AsyncMock(side_effect=err)),
        patch("app.services.ai_model_service.get_observability", return_value=obs),
    ):
        with pytest.raises(Exception):
            await acomplete_chat(
                litellm_model="openai/x",
                system_message="sys",
                user_message="usr",
                max_output_tokens=10,
                timeout_seconds=1.0,
                chain_provider="openai",
            )

    obs.record_error.assert_called_once()
