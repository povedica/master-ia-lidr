"""Helpers to read session state in integration tests."""

from __future__ import annotations

from app.services.sessions import InMemorySessionStore, Session


def get_session_state(store: InMemorySessionStore, session_id: str) -> Session:
    session = store.get_session(session_id)
    assert session is not None, f"session not found: {session_id}"
    return session


def messages_for_session(store: InMemorySessionStore, session_id: str) -> list[dict[str, str]]:
    return get_session_state(store, session_id).conversation_history.to_messages_list()
