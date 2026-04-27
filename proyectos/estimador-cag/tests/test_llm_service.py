"""LLM service and prompt construction tests."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from openai import APITimeoutError

from app.config import Settings
from app.context.examples import load_examples
from app.services.llm_service import EstimationError, EstimationService, build_system_prompt


def test_build_system_prompt_includes_both_example_summaries() -> None:
    examples = load_examples()
    prompt = build_system_prompt(examples)
    assert "Sales KPI dashboard" in prompt
    assert "Service marketplace MVP" in prompt
    assert "Reference estimation examples" in prompt


@pytest.mark.asyncio
async def test_estimate_rejects_empty_transcription() -> None:
    settings = Settings(openai_api_key="sk-test")
    service = EstimationService(settings)
    with pytest.raises(EstimationError, match="empty"):
        await service.estimate("   ")


@pytest.mark.asyncio
async def test_estimate_rejects_missing_api_key() -> None:
    settings = Settings(openai_api_key="")
    service = EstimationService(settings)
    with pytest.raises(EstimationError, match="not configured"):
        await service.estimate("some meeting text")


@pytest.mark.asyncio
async def test_estimate_maps_timeout_to_estimation_error() -> None:
    settings = Settings(openai_api_key="sk-test", openai_model="gpt-4o-mini")
    service = EstimationService(settings)

    mock_client = MagicMock()
    mock_client.chat.completions.create = AsyncMock(side_effect=APITimeoutError("timeout"))

    with patch("app.services.llm_service.AsyncOpenAI", return_value=mock_client):
        with pytest.raises(EstimationError, match="timed out"):
            await service.estimate("Client needs a portal.")


@pytest.mark.asyncio
async def test_estimate_returns_model_content() -> None:
    settings = Settings(openai_api_key="sk-test", openai_model="gpt-4o-mini")
    service = EstimationService(settings)

    mock_message = MagicMock()
    mock_message.content = "## Estimation: done"
    mock_choice = MagicMock()
    mock_choice.message = mock_message
    mock_response = MagicMock()
    mock_response.choices = [mock_choice]
    mock_response.usage = None

    mock_client = MagicMock()
    mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

    with patch("app.services.llm_service.AsyncOpenAI", return_value=mock_client):
        result = await service.estimate("Client needs a portal.")
    assert result.estimation.startswith("## Estimation")
    assert result.usage is None


@pytest.mark.asyncio
async def test_estimate_rejects_empty_model_message() -> None:
    settings = Settings(openai_api_key="sk-test", openai_model="gpt-4o-mini")
    service = EstimationService(settings)

    mock_message = MagicMock()
    mock_message.content = "   "
    mock_choice = MagicMock()
    mock_choice.message = mock_message
    mock_response = MagicMock()
    mock_response.choices = [mock_choice]

    mock_client = MagicMock()
    mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

    with patch("app.services.llm_service.AsyncOpenAI", return_value=mock_client):
        with pytest.raises(EstimationError, match="empty response"):
            await service.estimate("Client needs a portal.")
