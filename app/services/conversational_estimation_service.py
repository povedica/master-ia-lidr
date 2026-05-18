"""Orchestration for multi-turn conversational estimation sessions."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from app.config import Settings
from app.services.estimation_prompt_rendering import render_session_system_prompt
from app.services.llm_chain import LitellmChainProvider
from app.services.llm_service import EstimationError, EstimationService, LlmEstimationCallOutcome
from app.services.metadata_extractor import MetadataExtractionError, extract_and_merge_metadata
from app.services.sessions import InMemorySessionStore, Session


@dataclass(frozen=True)
class SessionEstimateOutcome:
    """Result of one conversational estimate turn."""

    session: Session
    estimation: LlmEstimationCallOutcome


class ConversationalEstimationService:
    """Load session state, run estimation, append history, and refresh metadata."""

    def __init__(
        self,
        settings: Settings,
        estimation_service: EstimationService,
        store: InMemorySessionStore,
    ) -> None:
        self._settings = settings
        self._estimation = estimation_service
        self._store = store

    async def run_turn(self, session_id: str, user_message: str) -> SessionEstimateOutcome:
        session = self._store.get_session(session_id)
        if session is None:
            raise SessionNotFoundError(session_id)

        text = user_message.strip()
        if not text:
            raise EstimationError("Transcription must not be empty.")

        prepared = await self._estimation._prepare_call(  # noqa: SLF001 — shared prelude for mode/guardrails
            text,
            preprocessing="none",
            assessment_input=text,
        )
        composed_system = render_session_system_prompt(
            prepared.system_prompt,
            session.project_metadata,
        )
        session.conversation_history.set_system_prompt(composed_system)
        session.conversation_history.add_user_message(text)

        outcome = await self._estimation.estimate(
            text,
            preprocessing="none",
            assessment_input=text,
            system_prompt_override=composed_system,
        )
        session.conversation_history.add_assistant_message(outcome.estimation)
        session.project_metadata = await self._extract_metadata(
            session.project_metadata,
            user_turn=text,
            assistant_turn=outcome.estimation,
        )
        session.updated_at = datetime.now(UTC)
        return SessionEstimateOutcome(session=session, estimation=outcome)

    async def _extract_metadata(
        self,
        current,
        *,
        user_turn: str,
        assistant_turn: str,
    ):
        provider = self._first_litellm_route()
        if provider is None:
            raise MetadataExtractionError(
                "Metadata extraction requires a live LiteLLM provider."
            )
        litellm_model, api_key, timeout = provider.litellm_route()
        return await extract_and_merge_metadata(
            current,
            user_turn=user_turn,
            assistant_turn=assistant_turn,
            litellm_model=litellm_model,
            chain_provider=provider.name,
            api_key=api_key,
            timeout_seconds=timeout,
            max_attempts=self._settings.structured_output_max_attempts,
        )

    def _first_litellm_route(self) -> LitellmChainProvider | None:
        for provider in self._estimation._providers:  # noqa: SLF001 — chain introspection
            if isinstance(provider, LitellmChainProvider):
                return provider
        return None


class SessionNotFoundError(LookupError):
    """Raised when the requested session id is absent from the store."""

    def __init__(self, session_id: str) -> None:
        super().__init__(f"Session not found: {session_id}")
        self.session_id = session_id
