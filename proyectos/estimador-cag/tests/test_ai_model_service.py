"""Tests for LiteLLM gateway helpers (acompletion is mocked)."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from litellm import exceptions as litellm_exc
from openai import APITimeoutError

from app.services.ai_model_service import acomplete_chat, astream_chat
from app.services.llm_types import (
    ProviderConfigError,
    ProviderInvalidResponseError,
    ProviderTimeoutError,
    ProviderUnavailableError,
)


def _delta_chunk(content: str) -> SimpleNamespace:
    """Build a LiteLLM-shaped streaming chunk with a single delta content string."""

    return SimpleNamespace(
        choices=[SimpleNamespace(delta=SimpleNamespace(content=content))]
    )


class _AsyncDeltaStream:
    """Minimal async iterator that yields the configured chunks in order."""

    def __init__(self, chunks: list[SimpleNamespace], raise_at: int | None = None,
                 error: BaseException | None = None) -> None:
        self._chunks = chunks
        self._raise_at = raise_at
        self._error = error
        self._index = 0

    def __aiter__(self) -> "_AsyncDeltaStream":
        return self

    async def __anext__(self) -> SimpleNamespace:
        if self._raise_at is not None and self._index == self._raise_at and self._error is not None:
            raise self._error
        if self._index >= len(self._chunks):
            raise StopAsyncIteration
        chunk = self._chunks[self._index]
        self._index += 1
        return chunk


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


@pytest.mark.asyncio
async def test_astream_chat_yields_each_delta_and_passes_stream_flag() -> None:
    captured: dict[str, object] = {}
    chunks = [_delta_chunk("Hello "), _delta_chunk("there"), _delta_chunk("!")]

    async def _fake_completion(**kwargs: object) -> object:
        captured.update(kwargs)
        return _AsyncDeltaStream(chunks)

    with patch("app.services.ai_model_service.acompletion", AsyncMock(side_effect=_fake_completion)):
        deltas = [
            delta
            async for delta in astream_chat(
                litellm_model="openai/gpt-4o-mini",
                system_message="sys",
                user_message="usr",
                max_output_tokens=128,
                timeout_seconds=10.0,
                chain_provider="openai",
                api_key="sk-test",
            )
        ]

    assert deltas == ["Hello ", "there", "!"]
    assert captured["stream"] is True
    assert captured["timeout"] == 10.0
    assert captured["api_key"] == "sk-test"


@pytest.mark.asyncio
async def test_astream_chat_skips_chunks_without_textual_delta() -> None:
    chunks = [
        _delta_chunk("partial"),
        SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content=None))]),
        _delta_chunk(" answer"),
    ]

    async def _fake_completion(**_: object) -> object:
        return _AsyncDeltaStream(chunks)

    with patch("app.services.ai_model_service.acompletion", AsyncMock(side_effect=_fake_completion)):
        deltas = [
            delta
            async for delta in astream_chat(
                litellm_model="openai/gpt-4o-mini",
                system_message="sys",
                user_message="usr",
                max_output_tokens=128,
                timeout_seconds=10.0,
                chain_provider="openai",
            )
        ]

    assert deltas == ["partial", " answer"]


@pytest.mark.asyncio
async def test_astream_chat_maps_open_phase_authentication_error() -> None:
    err = litellm_exc.AuthenticationError("no", llm_provider="openai", model="openai/x")
    with patch("app.services.ai_model_service.acompletion", AsyncMock(side_effect=err)):
        with pytest.raises(ProviderConfigError, match="OpenAI authentication"):
            async for _ in astream_chat(
                litellm_model="openai/x",
                system_message="sys",
                user_message="usr",
                max_output_tokens=10,
                timeout_seconds=1.0,
                chain_provider="openai",
                api_key="bad",
            ):
                pass


@pytest.mark.asyncio
async def test_astream_chat_maps_mid_stream_failure_to_provider_error() -> None:
    chunks = [_delta_chunk("first ")]
    rate_limit = litellm_exc.RateLimitError(
        "limit",
        "openai",
        "openai/x",
        response=httpx.Response(429, request=httpx.Request("POST", "https://api.openai.com")),
        litellm_debug_info=None,
    )

    async def _fake_completion(**_: object) -> object:
        return _AsyncDeltaStream(chunks, raise_at=1, error=rate_limit)

    with patch("app.services.ai_model_service.acompletion", AsyncMock(side_effect=_fake_completion)):
        collected: list[str] = []
        with pytest.raises(ProviderUnavailableError, match="rate limit"):
            async for delta in astream_chat(
                litellm_model="openai/x",
                system_message="sys",
                user_message="usr",
                max_output_tokens=10,
                timeout_seconds=1.0,
                chain_provider="openai",
            ):
                collected.append(delta)

    assert collected == ["first "]


@pytest.mark.asyncio
async def test_astream_chat_raises_when_stream_yields_no_text() -> None:
    async def _fake_completion(**_: object) -> object:
        return _AsyncDeltaStream([])

    with patch("app.services.ai_model_service.acompletion", AsyncMock(side_effect=_fake_completion)):
        with pytest.raises(ProviderInvalidResponseError, match="OpenAI returned an empty"):
            async for _ in astream_chat(
                litellm_model="openai/gpt-4o-mini",
                system_message="sys",
                user_message="usr",
                max_output_tokens=10,
                timeout_seconds=1.0,
                chain_provider="openai",
            ):
                pass


@pytest.mark.asyncio
async def test_astream_chat_rejects_empty_user_message_without_calling_provider() -> None:
    with patch("app.services.ai_model_service.acompletion", AsyncMock()) as mocked:
        with pytest.raises(ProviderInvalidResponseError, match="empty"):
            async for _ in astream_chat(
                litellm_model="openai/x",
                system_message="sys",
                user_message="   ",
                max_output_tokens=10,
                timeout_seconds=1.0,
                chain_provider="openai",
            ):
                pass
    mocked.assert_not_awaited()
