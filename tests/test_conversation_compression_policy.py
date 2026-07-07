"""Compression policy tests (feature-064)."""

from __future__ import annotations

from app.services.conversation_compression import AnchorDetector, CompressionPolicy, CumulativeSummarizer
from app.services.sessions import ConversationHistory


def test_compression_policy_preserves_anchor_turn() -> None:
    history = ConversationHistory(max_turns=2)
    policy = CompressionPolicy(
        anchor_detector=AnchorDetector(mode="heuristic"),
        summarizer=CumulativeSummarizer(),
    )
    history.enable_compression(policy)

    history.add_user_message("We agreed to lock the budget at 120k EUR.")
    history.add_assistant_message("Acknowledged.")
    for index in range(15):
        history.add_user_message(f"Turn {index} user question")
        history.add_assistant_message(f"Turn {index} assistant answer")

    rendered = history.to_messages_list()
    joined = "\n".join(message["content"] for message in rendered)
    assert "lock the budget" in joined


def test_conversation_history_without_compression_unchanged() -> None:
    history = ConversationHistory(max_turns=4)
    history.add_user_message("Scope question")
    history.add_assistant_message("Scope answer")
    history.add_user_message("Follow-up")
    history.add_assistant_message("Follow-up answer")

    expected = history.to_messages_list()
    assert len(expected) == 4
    assert expected[0]["content"] == "Scope question"
