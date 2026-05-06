"""Provider-specific tests with mocked LiteLLM gateway (acomplete_chat)."""

from unittest.mock import AsyncMock, patch

import pytest

from app.config import Settings
from app.context.prompt_loader import load_mode_prompt
from app.services.ai_model_service import LiteLLMChatOutcome
from app.services.estimation_engine import EstimationMode
from app.services.providers.anthropic_provider import AnthropicProvider
from app.services.providers.base import (
    ProviderConfigError,
    ProviderInvalidResponseError,
    ProviderTimeoutError,
    ProviderUnavailableError,
    UsageInfo,
)
from app.services.providers.openai_provider import OpenAIProvider
from app.services.providers.static_fallback import StaticFallbackProvider


@pytest.mark.asyncio
async def test_openai_provider_maps_timeout_to_provider_timeout_error() -> None:
    settings = Settings(openai_api_key="sk-test", openai_model="gpt-4o-mini")

    with patch(
        "app.services.providers.openai_provider.acomplete_chat",
        AsyncMock(side_effect=ProviderTimeoutError("OpenAI request timed out.")),
    ):
        provider = OpenAIProvider(settings)
        with pytest.raises(ProviderTimeoutError):
            await provider.complete("sys", "user", max_output_tokens=1024)


@pytest.mark.asyncio
async def test_openai_provider_raises_invalid_response_on_empty_message() -> None:
    settings = Settings(openai_api_key="sk-test", openai_model="gpt-4o-mini")
    with patch(
        "app.services.providers.openai_provider.acomplete_chat",
        AsyncMock(
            side_effect=ProviderInvalidResponseError("OpenAI returned an empty response."),
        ),
    ):
        provider = OpenAIProvider(settings)
        with pytest.raises(ProviderInvalidResponseError):
            await provider.complete("sys", "user", max_output_tokens=888)


@pytest.mark.asyncio
async def test_openai_provider_maps_preprocessing_tokens_from_usage() -> None:
    settings = Settings(openai_api_key="sk-test", openai_model="gpt-4o-mini")
    usage = UsageInfo(
        prompt_tokens=10,
        completion_tokens=5,
        total_tokens=15,
        preprocessing_input_tokens=3,
        preprocessing_output_tokens=1,
    )
    outcome = LiteLLMChatOutcome(
        text="## Estimation: ok",
        model="openai/gpt-4o-mini",
        usage=usage,
        finish_reason="stop",
    )
    mock_complete = AsyncMock(return_value=outcome)

    with patch("app.services.providers.openai_provider.acomplete_chat", mock_complete):
        provider = OpenAIProvider(settings)
        result = await provider.complete("sys", "user", max_output_tokens=512)

    assert result.usage is not None
    assert result.usage.preprocessing_input_tokens == 3
    assert result.usage.preprocessing_output_tokens == 1
    kwargs = mock_complete.await_args.kwargs
    assert kwargs["max_output_tokens"] == 512
    assert kwargs["litellm_model"] == "openai/gpt-4o-mini"


@pytest.mark.asyncio
async def test_openai_provider_maps_authentication_error_to_config_error() -> None:
    settings = Settings(openai_api_key="sk-test", openai_model="gpt-4o-mini")

    with patch(
        "app.services.providers.openai_provider.acomplete_chat",
        AsyncMock(side_effect=ProviderConfigError("OpenAI authentication failed.")),
    ):
        provider = OpenAIProvider(settings)
        with pytest.raises(ProviderConfigError):
            await provider.complete("sys", "user", max_output_tokens=1024)


@pytest.mark.asyncio
async def test_openai_provider_maps_rate_limit_to_unavailable_error() -> None:
    settings = Settings(openai_api_key="sk-test", openai_model="gpt-4o-mini")

    with patch(
        "app.services.providers.openai_provider.acomplete_chat",
        AsyncMock(side_effect=ProviderUnavailableError("OpenAI rate limit reached.")),
    ):
        provider = OpenAIProvider(settings)
        with pytest.raises(ProviderUnavailableError):
            await provider.complete("sys", "user", max_output_tokens=1024)


@pytest.mark.asyncio
async def test_anthropic_provider_delegates_via_acomplete_chat_messages() -> None:
    settings = Settings(
        anthropic_api_key="ak-test",
        anthropic_model="claude-3-5-haiku-latest",
    )
    usage = UsageInfo(
        prompt_tokens=11,
        completion_tokens=7,
        total_tokens=18,
        preprocessing_input_tokens=0,
        preprocessing_output_tokens=0,
    )
    outcome = LiteLLMChatOutcome(
        text="## Estimation: anthropic",
        model="anthropic/claude-3-5-haiku-latest",
        usage=usage,
        finish_reason="stop",
    )
    mock_complete = AsyncMock(return_value=outcome)

    with patch("app.services.providers.anthropic_provider.acomplete_chat", mock_complete):
        provider = AnthropicProvider(settings)
        result = await provider.complete("SYSTEM BLOCK", "USER TEXT", max_output_tokens=3200)

    assert result.provider == "anthropic"
    assert result.usage is not None
    assert result.usage.total_tokens == 18
    kwargs = mock_complete.await_args.kwargs
    assert kwargs["system_message"] == "SYSTEM BLOCK"
    assert kwargs["user_message"] == "USER TEXT"
    assert kwargs["max_output_tokens"] == 3200
    assert kwargs["litellm_model"] == "anthropic/claude-3-5-haiku-latest"


@pytest.mark.asyncio
async def test_anthropic_provider_maps_timeout() -> None:
    settings = Settings(
        anthropic_api_key="ak-test",
        anthropic_model="claude-3-5-haiku-latest",
    )

    with patch(
        "app.services.providers.anthropic_provider.acomplete_chat",
        AsyncMock(side_effect=ProviderTimeoutError("Anthropic request timed out.")),
    ):
        provider = AnthropicProvider(settings)
        with pytest.raises(ProviderTimeoutError):
            await provider.complete("sys", "user", max_output_tokens=1024)


@pytest.mark.asyncio
async def test_anthropic_provider_maps_authentication_error_to_config_error() -> None:
    settings = Settings(
        anthropic_api_key="ak-test",
        anthropic_model="claude-3-5-haiku-latest",
    )

    with patch(
        "app.services.providers.anthropic_provider.acomplete_chat",
        AsyncMock(side_effect=ProviderConfigError("Anthropic authentication failed.")),
    ):
        provider = AnthropicProvider(settings)
        with pytest.raises(ProviderConfigError):
            await provider.complete("sys", "user", max_output_tokens=1024)


@pytest.mark.asyncio
async def test_anthropic_provider_maps_not_found_to_config_error() -> None:
    settings = Settings(
        anthropic_api_key="ak-test",
        anthropic_model="claude-nonexistent-model",
    )

    with patch(
        "app.services.providers.anthropic_provider.acomplete_chat",
        AsyncMock(
            side_effect=ProviderConfigError(
                "Anthropic returned 404 for this model id (retired name, typo, or not enabled for your key).",
            ),
        ),
    ):
        provider = AnthropicProvider(settings)
        with pytest.raises(ProviderConfigError, match="404"):
            await provider.complete("sys", "user", max_output_tokens=1024)


@pytest.mark.asyncio
async def test_anthropic_provider_maps_rate_limit_to_unavailable_error() -> None:
    settings = Settings(
        anthropic_api_key="ak-test",
        anthropic_model="claude-3-5-haiku-latest",
    )

    with patch(
        "app.services.providers.anthropic_provider.acomplete_chat",
        AsyncMock(side_effect=ProviderUnavailableError("Anthropic rate limit reached.")),
    ):
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
