"""Unit tests for conversational estimation orchestration."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.config import Settings
from app.services.conversational_estimation_service import (
    ConversationalEstimationService,
    SessionNotFoundError,
)
from app.services.llm_service import EstimationService, LlmEstimationCallOutcome, UsageInfo
from app.services.sessions import InMemorySessionStore, ProjectMetadata


@pytest.fixture
def store() -> InMemorySessionStore:
    return InMemorySessionStore()


@pytest.fixture
def settings() -> Settings:
    return Settings(
        openai_api_key="test-key",
        llm_domain_guardrail_enabled=False,
    )


def _fake_outcome(text: str = "## Estimation\n\nDone.") -> LlmEstimationCallOutcome:
    return LlmEstimationCallOutcome(
        estimation=text,
        provider="openai",
        model="gpt-4o-mini",
        usage=UsageInfo(prompt_tokens=10, completion_tokens=5, total_tokens=15),
        finish_reason="stop",
    )


@pytest.mark.asyncio
async def test_run_turn_updates_history_metadata_and_timestamp(
    store: InMemorySessionStore,
    settings: Settings,
) -> None:
    session = store.create_session()
    estimation_service = MagicMock(spec=EstimationService)
    estimation_service._providers = []
    estimation_service._prepare_call = AsyncMock(
        return_value=MagicMock(system_prompt="Base system.", user_text="Build API")
    )
    estimation_service.estimate = AsyncMock(return_value=_fake_outcome())

    service = ConversationalEstimationService(settings, estimation_service, store)

    with patch(
        "app.services.conversational_estimation_service.render_session_system_prompt",
        return_value="Base system.\n\n## Metadata",
    ) as render_mock, patch.object(
        service,
        "_extract_metadata",
        new_callable=AsyncMock,
        return_value=ProjectMetadata(project_name="API"),
    ):
        outcome = await service.run_turn(session.session_id, "Build API")

    render_mock.assert_called_once()
    assert outcome.estimation.estimation.startswith("## Estimation")
    messages = outcome.session.conversation_history.to_messages_list()
    assert messages[0]["content"] == "Base system.\n\n## Metadata"
    assert messages[-2]["role"] == "user"
    assert messages[-1]["role"] == "assistant"
    assert outcome.session.project_metadata.project_name == "API"
    assert outcome.session.updated_at >= outcome.session.created_at


@pytest.mark.asyncio
async def test_run_turn_raises_when_session_missing(store: InMemorySessionStore, settings: Settings) -> None:
    estimation_service = MagicMock(spec=EstimationService)
    service = ConversationalEstimationService(settings, estimation_service, store)

    with pytest.raises(SessionNotFoundError):
        await service.run_turn("missing-id", "hello")
