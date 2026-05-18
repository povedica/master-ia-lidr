"""In-memory conversational session state for multi-turn estimation.

Trade-off: process-local only; no persistence across restarts or workers.
Future HTTP session routes should use the module-level ``session_store`` singleton.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.estimation_request import EstimationRequest

ChatRole = Literal["system", "user", "assistant"]


@dataclass(frozen=True)
class ChatMessage:
    """Single chat turn as a plain role/content pair."""

    role: ChatRole
    content: str


class ConversationHistory:
    """Bounded message history that always keeps the system prompt first."""

    def __init__(self, max_turns: int = 10) -> None:
        self.max_turns = max_turns
        self._system: ChatMessage | None = None
        self._turns: list[ChatMessage] = []

    def set_system_prompt(self, content: str) -> None:
        self._system = ChatMessage(role="system", content=content)

    def add_user_message(self, content: str) -> None:
        self._turns.append(ChatMessage(role="user", content=content))
        self._enforce_window()

    def add_assistant_message(self, content: str) -> None:
        self._turns.append(ChatMessage(role="assistant", content=content))
        self._enforce_window()

    def to_messages_list(self) -> list[dict[str, str]]:
        messages: list[dict[str, str]] = []
        if self._system is not None:
            messages.append({"role": self._system.role, "content": self._system.content})
        for message in self._turns:
            messages.append({"role": message.role, "content": message.content})
        return messages

    def _enforce_window(self) -> None:
        while len(self._turns) // 2 > self.max_turns:
            del self._turns[0:2]


class ProjectMetadata(BaseModel):
    """Facts extracted during a conversation; all fields optional."""

    model_config = ConfigDict(frozen=False)

    project_name: str | None = None
    assumed_team_size: int | None = None
    mentioned_technologies: list[str] = Field(default_factory=list)
    agreed_scope: str | None = None
    explicit_constraints: list[str] = Field(default_factory=list)
    rejected_options: list[str] = Field(default_factory=list)


@dataclass
class Session:
    """Aggregate session state: identity, history, and project facts."""

    session_id: str
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    conversation_history: ConversationHistory = field(default_factory=ConversationHistory)
    project_metadata: ProjectMetadata = field(default_factory=ProjectMetadata)
    last_estimation_request: EstimationRequest | None = None
    submit_count: int = 0


class InMemorySessionStore:
    """Encapsulated in-process session registry keyed by session id."""

    def __init__(self) -> None:
        self._sessions: dict[str, Session] = {}

    def create_session(self) -> Session:
        session_id = str(uuid.uuid4())
        session = Session(session_id=session_id)
        self._sessions[session_id] = session
        return session

    def get_session(self, session_id: str) -> Session | None:
        return self._sessions.get(session_id)

    def exists(self, session_id: str) -> bool:
        return session_id in self._sessions

    def delete_session(self, session_id: str) -> None:
        self._sessions.pop(session_id, None)

    def list_sessions(self) -> list[Session]:
        """Return all sessions ordered by ``updated_at`` descending (most recent first)."""

        return sorted(
            self._sessions.values(),
            key=lambda session: session.updated_at,
            reverse=True,
        )


session_store = InMemorySessionStore()
