"""Tests for LiteLLM gateway helpers (acompletion is mocked)."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from litellm import exceptions as litellm_exc
from openai import APITimeoutError

from app.services.ai_model_service import acomplete_chat
from app.services.llm_types import (
    ProviderConfigError,
    ProviderInvalidResponseError,
    ProviderTimeoutError,
    ProviderUnavailableError,
)


@pytest.mark.asyncio
async def test_acomplete_chat_returns_normalized_outcome_with_usage() -> None:
    mock_usage = SimpleNamespace(
        prompt_tokens=10,
        completion_tokens=5,
        total_tokens=15,
        preprocessing_input_tokens=1,
        preprocessing_output_tokens=0,
    )
    mock_message = SimpleNamespace(content="  hello  ")
    mock_choice = SimpleNamespace(message=mock_message, finish_reason="stop")
    mock_resp = SimpleNamespace(
        choices=[mock_choice],
        model="openai/gpt-4o-mini",
        usage=mock_usage,
    )
    captured: dict[str, object] = {}

    async def _fake_completion(**kwargs: object) -> object:
        captured.update(kwargs)
        return mock_resp

    with patch("app.services.ai_model_service.acompletion", AsyncMock(side_effect=_fake_completion)):
        out = await acomplete_chat(
            litellm_model="openai/gpt-4o-mini",
            system_message="sys",
            user_message="usr",
            max_output_tokens=256,
            timeout_seconds=12.0,
            chain_provider="openai",
            api_key="sk-test",
        )

    assert out.text == "hello"
    assert out.model == "openai/gpt-4o-mini"
    assert out.finish_reason == "stop"
    assert out.usage is not None
    assert out.usage.prompt_tokens == 10
    assert out.usage.total_tokens == 15
    assert captured["timeout"] == 12.0
    assert captured["api_key"] == "sk-test"
    msgs = captured["messages"]
    assert isinstance(msgs, list)
    assert msgs[0]["role"] == "system"
    assert msgs[1]["role"] == "user"


@pytest.mark.asyncio
async def test_acomplete_chat_maps_authentication_error() -> None:
    err = litellm_exc.AuthenticationError("no", llm_provider="openai", model="openai/x")
    with patch("app.services.ai_model_service.acompletion", AsyncMock(side_effect=err)):
        with pytest.raises(ProviderConfigError, match="OpenAI authentication"):
            await acomplete_chat(
                litellm_model="openai/x",
                system_message="sys",
                user_message="usr",
                max_output_tokens=10,
                timeout_seconds=1.0,
                chain_provider="openai",
                api_key="bad",
            )


@pytest.mark.asyncio
async def test_acomplete_chat_maps_openai_timeout() -> None:
    http_request = httpx.Request("POST", "https://api.openai.com")
    exc = APITimeoutError(request=http_request)
    with patch("app.services.ai_model_service.acompletion", AsyncMock(side_effect=exc)):
        with pytest.raises(ProviderTimeoutError, match="OpenAI request timed out"):
            await acomplete_chat(
                litellm_model="openai/x",
                system_message="sys",
                user_message="usr",
                max_output_tokens=10,
                timeout_seconds=1.0,
                chain_provider="openai",
            )


@pytest.mark.asyncio
async def test_acomplete_chat_raises_on_empty_user_message() -> None:
    with patch("app.services.ai_model_service.acompletion", AsyncMock()) as mocked:
        with pytest.raises(ProviderInvalidResponseError, match="empty"):
            await acomplete_chat(
                litellm_model="openai/x",
                system_message="sys",
                user_message="   ",
                max_output_tokens=10,
                timeout_seconds=1.0,
                chain_provider="openai",
            )
    mocked.assert_not_awaited()


@pytest.mark.asyncio
async def test_acomplete_chat_maps_rate_limit_error() -> None:
    err = litellm_exc.RateLimitError(
        "limit",
        "openai",
        "openai/x",
        response=httpx.Response(429, request=httpx.Request("POST", "https://api.openai.com")),
        litellm_debug_info=None,
    )
    with patch("app.services.ai_model_service.acompletion", AsyncMock(side_effect=err)):
        with pytest.raises(ProviderUnavailableError, match="rate limit"):
            await acomplete_chat(
                litellm_model="openai/x",
                system_message="sys",
                user_message="usr",
                max_output_tokens=10,
                timeout_seconds=1.0,
                chain_provider="openai",
            )


@pytest.mark.asyncio
async def test_acomplete_chat_maps_empty_completion_to_invalid_response() -> None:
    mock_message = SimpleNamespace(content="   ")
    mock_choice = SimpleNamespace(message=mock_message, finish_reason="stop")
    mock_resp = SimpleNamespace(
        choices=[mock_choice],
        model="openai/gpt-4o-mini",
        usage=None,
    )
    with patch("app.services.ai_model_service.acompletion", AsyncMock(return_value=mock_resp)):
        with pytest.raises(ProviderInvalidResponseError, match="OpenAI returned an empty"):
            await acomplete_chat(
                litellm_model="openai/gpt-4o-mini",
                system_message="sys",
                user_message="usr",
                max_output_tokens=10,
                timeout_seconds=1.0,
                chain_provider="openai",
            )
