"""Provider-specific tests with mocked SDK clients."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from anthropic import (
    APITimeoutError as AnthropicTimeoutError,
    AuthenticationError as AnthropicAuthenticationError,
    RateLimitError as AnthropicRateLimitError,
)
from openai import (
    APITimeoutError as OpenAITimeoutError,
    AuthenticationError as OpenAIAuthenticationError,
    RateLimitError as OpenAIRateLimitError,
)

from app.config import Settings
from app.services.providers.anthropic_provider import AnthropicProvider
from app.services.providers.base import (
    ProviderConfigError,
    ProviderInvalidResponseError,
    ProviderTimeoutError,
    ProviderUnavailableError,
)
from app.context.prompt_loader import load_mode_prompt
from app.services.estimation_engine import EstimationMode
from app.services.providers.openai_provider import OpenAIProvider
from app.services.providers.static_fallback import StaticFallbackProvider


def _api_status_error(error_cls: type[Exception]) -> Exception:
    response = MagicMock()
    response.request = MagicMock()
    return error_cls("failure", response=response, body={})


@pytest.mark.asyncio
async def test_openai_provider_maps_timeout_to_provider_timeout_error() -> None:
    settings = Settings(openai_api_key="sk-test", openai_model="gpt-4o-mini")
    mock_client = MagicMock()
    mock_client.chat.completions.create = AsyncMock(side_effect=OpenAITimeoutError("timeout"))

    with patch("app.services.providers.openai_provider.AsyncOpenAI", return_value=mock_client):
        provider = OpenAIProvider(settings)
        with pytest.raises(ProviderTimeoutError):
            await provider.complete("sys", "user", max_output_tokens=1024)


@pytest.mark.asyncio
async def test_openai_provider_raises_invalid_response_on_empty_message() -> None:
    settings = Settings(openai_api_key="sk-test", openai_model="gpt-4o-mini")
    mock_message = MagicMock()
    mock_message.content = "   "
    mock_choice = MagicMock()
    mock_choice.message = mock_message
    mock_response = MagicMock()
    mock_response.choices = [mock_choice]
    mock_response.usage = None

    mock_client = MagicMock()
    mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

    with patch("app.services.providers.openai_provider.AsyncOpenAI", return_value=mock_client):
        provider = OpenAIProvider(settings)
        with pytest.raises(ProviderInvalidResponseError):
            await provider.complete("sys", "user", max_output_tokens=888)
    kwargs = mock_client.chat.completions.create.await_args.kwargs
    assert kwargs["max_completion_tokens"] == 888


@pytest.mark.asyncio
async def test_openai_provider_maps_authentication_error_to_config_error() -> None:
    settings = Settings(openai_api_key="sk-test", openai_model="gpt-4o-mini")
    mock_client = MagicMock()
    mock_client.chat.completions.create = AsyncMock(
        side_effect=_api_status_error(OpenAIAuthenticationError),
    )

    with patch("app.services.providers.openai_provider.AsyncOpenAI", return_value=mock_client):
        provider = OpenAIProvider(settings)
        with pytest.raises(ProviderConfigError):
            await provider.complete("sys", "user", max_output_tokens=1024)


@pytest.mark.asyncio
async def test_openai_provider_maps_rate_limit_to_unavailable_error() -> None:
    settings = Settings(openai_api_key="sk-test", openai_model="gpt-4o-mini")
    mock_client = MagicMock()
    mock_client.chat.completions.create = AsyncMock(
        side_effect=_api_status_error(OpenAIRateLimitError),
    )

    with patch("app.services.providers.openai_provider.AsyncOpenAI", return_value=mock_client):
        provider = OpenAIProvider(settings)
        with pytest.raises(ProviderUnavailableError):
            await provider.complete("sys", "user", max_output_tokens=1024)


@pytest.mark.asyncio
async def test_anthropic_provider_uses_system_as_top_level_argument() -> None:
    settings = Settings(
        anthropic_api_key="ak-test",
        anthropic_model="claude-3-5-haiku-latest",
    )
    mock_response = SimpleNamespace(
        content=[SimpleNamespace(type="text", text="## Estimation: anthropic")],
        usage=SimpleNamespace(input_tokens=11, output_tokens=7),
    )
    mock_client = MagicMock()
    mock_client.messages.create = AsyncMock(return_value=mock_response)

    with patch("app.services.providers.anthropic_provider.AsyncAnthropic", return_value=mock_client):
        provider = AnthropicProvider(settings)
        result = await provider.complete("SYSTEM BLOCK", "USER TEXT", max_output_tokens=3200)

    assert result.provider == "anthropic"
    assert result.usage is not None
    assert result.usage.total_tokens == 18
    kwargs = mock_client.messages.create.await_args.kwargs
    assert kwargs["system"] == "SYSTEM BLOCK"
    assert kwargs["messages"] == [{"role": "user", "content": "USER TEXT"}]
    assert kwargs["max_tokens"] == 3200


@pytest.mark.asyncio
async def test_anthropic_provider_maps_timeout() -> None:
    settings = Settings(
        anthropic_api_key="ak-test",
        anthropic_model="claude-3-5-haiku-latest",
    )
    mock_client = MagicMock()
    mock_client.messages.create = AsyncMock(side_effect=AnthropicTimeoutError("timeout"))

    with patch("app.services.providers.anthropic_provider.AsyncAnthropic", return_value=mock_client):
        provider = AnthropicProvider(settings)
        with pytest.raises(ProviderTimeoutError):
            await provider.complete("sys", "user", max_output_tokens=1024)


@pytest.mark.asyncio
async def test_anthropic_provider_maps_authentication_error_to_config_error() -> None:
    settings = Settings(
        anthropic_api_key="ak-test",
        anthropic_model="claude-3-5-haiku-latest",
    )
    mock_client = MagicMock()
    mock_client.messages.create = AsyncMock(
        side_effect=_api_status_error(AnthropicAuthenticationError),
    )

    with patch("app.services.providers.anthropic_provider.AsyncAnthropic", return_value=mock_client):
        provider = AnthropicProvider(settings)
        with pytest.raises(ProviderConfigError):
            await provider.complete("sys", "user", max_output_tokens=1024)


@pytest.mark.asyncio
async def test_anthropic_provider_maps_rate_limit_to_unavailable_error() -> None:
    settings = Settings(
        anthropic_api_key="ak-test",
        anthropic_model="claude-3-5-haiku-latest",
    )
    mock_client = MagicMock()
    mock_client.messages.create = AsyncMock(
        side_effect=_api_status_error(AnthropicRateLimitError),
    )

    with patch("app.services.providers.anthropic_provider.AsyncAnthropic", return_value=mock_client):
        provider = AnthropicProvider(settings)
        with pytest.raises(ProviderUnavailableError):
            await provider.complete("sys", "user", max_output_tokens=1024)


@pytest.mark.asyncio
async def test_static_fallback_provider_returns_degraded_payload() -> None:
    provider = StaticFallbackProvider()
    result = await provider.complete("sys", "user", max_output_tokens=256)
    assert result.provider == "static_fallback"
    assert result.model == "static-v1"
    assert result.usage is None
    assert "degraded mode" in result.text.lower()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("mode", "must_contain", "must_not_contain"),
    [
        (EstimationMode.BASIC, "## mvp scope", "## budget (indicative)"),
        (EstimationMode.STANDARD, "## budget (indicative)", "scenario bands"),
        (EstimationMode.PROFESSIONAL, "scenario bands", "worst case: 40 hours"),
        (
            EstimationMode.EXPERT_REVIEW,
            "## profile breakdown",
            "scenario bands",
        ),
    ],
)
async def test_static_fallback_budget_shape_follows_mode(
    mode: EstimationMode,
    must_contain: str,
    must_not_contain: str,
) -> None:
    """Degraded markdown should mirror live-mode budget expectations (range vs breakdown)."""

    system = load_mode_prompt(mode)
    result = await StaticFallbackProvider().complete(system, "user", max_output_tokens=512)
    lowered = result.text.lower()
    assert must_contain in lowered
    assert must_not_contain not in lowered
