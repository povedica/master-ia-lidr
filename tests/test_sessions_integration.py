"""Integration tests for session memory, metadata, and attachments."""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient

from app.services.sessions import InMemorySessionStore, ProjectMetadata
from tests.fakes.fake_llm_provider import FakeStructuredLLM
from tests.fixtures.attachment_bytes import redis_marker_attachment_ref
from tests.fixtures.session_store import get_session_state, messages_for_session
from tests.fixtures.transcripts import TURN_1, TURN_2, build_transcript, simplified_submit_payload

pytest_plugins = ["tests.fixtures.conftest_sessions"]


def assert_window(messages: list[dict[str, str]], *, max_turns: int) -> None:
    assert messages[0]["role"] == "system"
    non_system = messages[1:]
    assert len(non_system) <= max_turns * 2
    roles = [message["role"] for message in non_system]
    expected = ["user", "assistant"] * (len(non_system) // 2)
    assert roles == expected


@pytest.mark.asyncio
async def test_create_session_initializes_empty_state(
    async_client: AsyncClient,
    session_store: InMemorySessionStore,
) -> None:
    first = await async_client.post("/api/v1/sessions")
    second = await async_client.post("/api/v1/sessions")

    assert first.status_code == 201
    assert second.status_code == 201
    session_id = first.json()["session_id"]
    other_id = second.json()["session_id"]
    uuid.UUID(session_id)
    uuid.UUID(other_id)
    assert session_id != other_id
    assert session_store.exists(session_id)

    session = get_session_state(session_store, session_id)
    assert session.conversation_history.to_messages_list() == []
    assert session.project_metadata == ProjectMetadata()
    assert session.submit_count == 0


@pytest.mark.asyncio
async def test_two_linked_submits_enrich_metadata_and_inject_into_system_prompt(
    async_client: AsyncClient,
    session_store: InMemorySessionStore,
    fake_structured_llm: FakeStructuredLLM,
) -> None:
    created = await async_client.post("/api/v1/sessions")
    session_id = created.json()["session_id"]

    turn_1 = await async_client.post(
        f"/api/v1/sessions/{session_id}/estimate",
        json=TURN_1,
    )
    assert turn_1.status_code == 200
    assert turn_1.json()["project_metadata"]["project_name"] == "Acme Portal"

    session = get_session_state(session_store, session_id)
    assert session.project_metadata.project_name == "Acme Portal"
    history_after_1 = session.conversation_history.to_messages_list()
    assert len(history_after_1) >= 3
    assert fake_structured_llm.last_call().system_prompt.count("Acme Portal") >= 1
    assert TURN_1["transcript"][:40] in fake_structured_llm.last_call().user_prompt

    turn_2 = await async_client.post(
        f"/api/v1/sessions/{session_id}/estimate",
        json=TURN_2,
    )
    assert turn_2.status_code == 200
    assert turn_2.json()["project_metadata"]["project_name"] == "Acme Portal"
    assert fake_structured_llm.last_call().system_prompt.count("Acme Portal") >= 1

    history = messages_for_session(session_store, session_id)
    assert history[0]["role"] == "system"
    user_contents = [message["content"] for message in history if message["role"] == "user"]
    assert len(user_contents) == 2
    assert all("[Simplified submit] Acme Portal" in content for content in user_contents)
    assert "Redis" in fake_structured_llm.calls[1].user_prompt
    assert len(fake_structured_llm.calls) == 2


@pytest.mark.asyncio
async def test_attachment_text_influences_llm_prompt_and_estimate(
    async_client: AsyncClient,
    fake_structured_llm: FakeStructuredLLM,
) -> None:
    created = await async_client.post("/api/v1/sessions")
    session_id = created.json()["session_id"]
    payload = simplified_submit_payload(
        project_name="Acme Portal",
        transcript="See attached addendum for caching requirements. " * 4,
        attachments=[redis_marker_attachment_ref()],
    )

    response = await async_client.post(
        f"/api/v1/sessions/{session_id}/estimate",
        json=payload,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["attachments"][0]["status"] == "processed"
    assert "redis_addendum.txt" in (body["project_metadata"].get("attachment_summary") or "")
    prompt = fake_structured_llm.last_call().user_prompt
    assert "<attachments>" in prompt
    assert 'filename="redis_addendum.txt"' in prompt
    assert "ATTACH_MARKER:USE_REDIS" in prompt
    line_names = [item["name"] for item in body["estimate"]["result"]["line_items"]]
    assert "Redis (from attachment)" in line_names


@pytest.mark.asyncio
async def test_attachment_missing_does_not_inject_marker(
    async_client: AsyncClient,
) -> None:
    created = await async_client.post("/api/v1/sessions")
    session_id = created.json()["session_id"]
    payload = simplified_submit_payload(
        project_name="Acme Portal",
        transcript="See attached addendum for caching requirements. " * 4,
    )

    response = await async_client.post(
        f"/api/v1/sessions/{session_id}/estimate",
        json=payload,
    )

    assert response.status_code == 200
    line_names = [item["name"] for item in response.json()["estimate"]["result"]["line_items"]]
    assert "Redis (from attachment)" not in line_names


@pytest.mark.asyncio
async def test_sliding_window_drops_oldest_pairs_preserves_system_prompt(
    async_client: AsyncClient,
    session_store: InMemorySessionStore,
) -> None:
    created = await async_client.post("/api/v1/sessions")
    session_id = created.json()["session_id"]
    session = get_session_state(session_store, session_id)
    session.conversation_history.max_turns = 3
    session.project_metadata.project_name = "Window Project"

    for index in range(1, 8):
        marker = f"TURN_MARKER:{index:02d}"
        payload = simplified_submit_payload(
            project_name="Window Project",
            transcript=build_transcript(marker=marker),
        )
        response = await async_client.post(
            f"/api/v1/sessions/{session_id}/estimate",
            json=payload,
        )
        assert response.status_code == 200

    history = messages_for_session(session_store, session_id)
    assert_window(history, max_turns=3)
    joined = "\n".join(message["content"] for message in history)
    assert "TURN_MARKER:01" not in joined
    assert "TURN_MARKER:02" not in joined
    assert "TURN_MARKER:07" in joined
    assert get_session_state(session_store, session_id).project_metadata.project_name == "Window Project"


@pytest.mark.asyncio
async def test_unknown_session_returns_404(
    async_client: AsyncClient,
    session_store: InMemorySessionStore,
) -> None:
    missing_id = str(uuid.uuid4())
    assert not session_store.exists(missing_id)
    response = await async_client.post(
        f"/api/v1/sessions/{missing_id}/estimate",
        json=simplified_submit_payload(),
    )
    assert response.status_code == 404
    assert not session_store.exists(missing_id)


@pytest.mark.asyncio
async def test_session_isolation(
    async_client: AsyncClient,
    session_store: InMemorySessionStore,
) -> None:
    session_a = (await async_client.post("/api/v1/sessions")).json()["session_id"]
    session_b = (await async_client.post("/api/v1/sessions")).json()["session_id"]

    enriched = await async_client.post(
        f"/api/v1/sessions/{session_a}/estimate",
        json=TURN_1,
    )
    assert enriched.status_code == 200

    session_b_state = get_session_state(session_store, session_b)
    assert session_b_state.project_metadata.project_name is None
    assert session_b_state.submit_count == 0
