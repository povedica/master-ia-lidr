"""In-memory conversational session state for multi-turn estimation.

Trade-off: process-local only; no persistence across restarts or workers.
Future HTTP session routes should use the module-level ``session_store`` singleton.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.estimation_request import Industry, ProjectType, TargetAudience

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
        self.anchors: list[ChatMessage] = []
        self.summary: str | None = None
        self._compression_enabled = False
        self._compression_policy: object | None = None

    @property
    def turns(self) -> list[ChatMessage]:
        return self._turns

    def enable_compression(self, policy: object) -> None:
        self._compression_enabled = True
        self._compression_policy = policy

    def set_system_prompt(self, content: str) -> None:
        self._system = ChatMessage(role="system", content=content)

    def add_user_message(self, content: str) -> None:
        self._turns.append(ChatMessage(role="user", content=content))
        if not self._compression_enabled:
            self._enforce_window()

    def add_assistant_message(self, content: str) -> None:
        self._turns.append(ChatMessage(role="assistant", content=content))
        if self._compression_enabled and self._compression_policy is not None:
            self._compression_policy.apply(self)
        else:
            self._enforce_window()

    def to_messages_list(self) -> list[dict[str, str]]:
        messages: list[dict[str, str]] = []
        if self._system is not None:
            messages.append({"role": self._system.role, "content": self._system.content})
        if self.summary:
            messages.append(
                {
                    "role": "user",
                    "content": f"[Session summary]\n{self.summary}",
                }
            )
        for message in self.anchors:
            messages.append({"role": message.role, "content": message.content})
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


class DerivedProjectMetadata(BaseModel):
    """UI-facing project memory returned from simplified session submits."""

    model_config = ConfigDict(frozen=False)

    project_name: str
    project_type: ProjectType
    target_audience: TargetAudience
    industry: Industry | None = None
    summary: str | None = None
    detected_constraints: list[str] = Field(default_factory=list)
    attachment_summary: str | None = None
    confidence_notes: list[str] = Field(default_factory=list)


@dataclass
class Session:
    """Aggregate session state: identity, history, and project facts."""

    session_id: str
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    conversation_history: ConversationHistory = field(default_factory=ConversationHistory)
    project_metadata: ProjectMetadata = field(default_factory=ProjectMetadata)
    last_normalized_payload: dict[str, Any] | None = None
    last_derived_metadata: DerivedProjectMetadata | None = None
    last_attachment_statuses: list[Any] = field(default_factory=list)
    last_estimate: dict[str, Any] | None = None
    last_warnings: list[str] = field(default_factory=list)
    last_turn_observation: dict[str, Any] | None = None
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

    def list_sessions(self, *, max_age_days: int = 30) -> list[Session]:
        """Return sessions updated within the window, newest first."""

        cutoff = datetime.now(UTC) - timedelta(days=max_age_days)
        recent = [session for session in self._sessions.values() if session.updated_at >= cutoff]
        return sorted(recent, key=lambda session: session.updated_at, reverse=True)

    def reset_for_tests(self) -> None:
        """Clear all sessions; use only from pytest fixtures."""

        self._sessions.clear()


def session_display_label(session: Session) -> str:
    """Human label for sidebar rows from derived or submitted payload."""

    if session.last_derived_metadata is not None:
        return session.last_derived_metadata.project_name
    payload = session.last_normalized_payload
    if isinstance(payload, dict):
        name = payload.get("project_name")
        if isinstance(name, str) and name.strip():
            return name.strip()
    return "Untitled session"


session_store = InMemorySessionStore()
