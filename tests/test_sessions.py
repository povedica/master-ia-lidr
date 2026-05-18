"""Unit tests for in-memory conversational session state."""

from __future__ import annotations

from app.services.sessions import (
    ChatMessage,
    ConversationHistory,
    InMemorySessionStore,
    ProjectMetadata,
    Session,
)


def test_project_metadata_defaults_are_optional() -> None:
    meta = ProjectMetadata()
    assert meta.project_name is None
    assert meta.assumed_team_size is None
    assert meta.mentioned_technologies == []
    assert meta.agreed_scope is None
    assert meta.explicit_constraints == []
    assert meta.rejected_options == []


def test_session_has_updated_at_defaulting_near_created_at() -> None:
    session = Session(session_id="sess-updated")
    assert session.updated_at is not None
    assert session.updated_at.tzinfo is not None
    delta = abs((session.updated_at - session.created_at).total_seconds())
    assert delta < 1.0


def test_chat_message_is_frozen_value() -> None:
    msg = ChatMessage(role="user", content="hello")
    assert msg.role == "user"
    assert msg.content == "hello"


def test_conversation_history_to_messages_list_includes_system_first() -> None:
    history = ConversationHistory(max_turns=4)
    history.set_system_prompt("You are an estimator.")
    history.add_user_message("Build a login form.")
    history.add_assistant_message("Roughly 3 days.")

    messages = history.to_messages_list()

    assert messages[0] == {"role": "system", "content": "You are an estimator."}
    assert messages[1:] == [
        {"role": "user", "content": "Build a login form."},
        {"role": "assistant", "content": "Roughly 3 days."},
    ]


def test_conversation_history_preserves_system_when_window_exceeded() -> None:
    history = ConversationHistory(max_turns=2)
    history.set_system_prompt("System stays.")
    history.add_user_message("u1")
    history.add_assistant_message("a1")
    history.add_user_message("u2")
    history.add_assistant_message("a2")
    history.add_user_message("u3")
    history.add_assistant_message("a3")

    messages = history.to_messages_list()

    assert messages[0] == {"role": "system", "content": "System stays."}


def test_conversation_history_drops_oldest_turn_pair_when_window_exceeded() -> None:
    history = ConversationHistory(max_turns=2)
    history.set_system_prompt("sys")
    history.add_user_message("u1")
    history.add_assistant_message("a1")
    history.add_user_message("u2")
    history.add_assistant_message("a2")
    history.add_user_message("u3")
    history.add_assistant_message("a3")

    messages = history.to_messages_list()

    assert {"role": "user", "content": "u1"} not in messages
    assert {"role": "assistant", "content": "a1"} not in messages
    assert messages[-2:] == [
        {"role": "user", "content": "u3"},
        {"role": "assistant", "content": "a3"},
    ]


def test_session_initializes_with_empty_history_and_default_metadata() -> None:
    session = Session(session_id="sess-1")

    assert session.session_id == "sess-1"
    assert session.conversation_history.to_messages_list() == []
    assert session.project_metadata == ProjectMetadata()


def test_in_memory_session_store_create_get_and_delete() -> None:
    store = InMemorySessionStore()
    session = store.create_session()

    assert store.exists(session.session_id)
    assert store.get_session(session.session_id) is session

    store.delete_session(session.session_id)
    assert store.get_session(session.session_id) is None
    assert store.exists(session.session_id) is False


def test_in_memory_session_store_get_unknown_returns_none() -> None:
    store = InMemorySessionStore()
    assert store.get_session("missing") is None


def test_in_memory_session_store_delete_missing_is_idempotent() -> None:
    store = InMemorySessionStore()
    store.delete_session("missing")


def test_project_metadata_survives_conversation_history_trim() -> None:
    session = Session(session_id="sess-trim")
    session.project_metadata = ProjectMetadata(project_name="Persistent Portal")
    history = session.conversation_history
    history.max_turns = 1
    history.set_system_prompt("sys")
    history.add_user_message("u1")
    history.add_assistant_message("a1")
    history.add_user_message("u2")
    history.add_assistant_message("a2")

    assert session.project_metadata.project_name == "Persistent Portal"
    assert {"role": "user", "content": "u1"} not in history.to_messages_list()
