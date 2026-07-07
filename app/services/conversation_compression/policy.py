"""Compression policy for bounded session history (feature-064)."""

from __future__ import annotations

import logging

from app.services.conversation_compression.anchors import AnchorDetector
from app.services.conversation_compression.summarizer import CumulativeSummarizer
from app.services.sessions import ChatMessage, ConversationHistory

logger = logging.getLogger(__name__)


class CompressionPolicy:
    def __init__(
        self,
        *,
        anchor_detector: AnchorDetector,
        summarizer: CumulativeSummarizer,
    ) -> None:
        self._anchor_detector = anchor_detector
        self._summarizer = summarizer

    def apply(self, history: ConversationHistory) -> None:
        if len(history.turns) <= history.max_turns * 2:
            return

        evicted_for_summary: list[ChatMessage] = []
        while len(history.turns) > history.max_turns * 2:
            if len(history.turns) < 2:
                break
            user_msg = history.turns[0]
            assistant_msg = history.turns[1]
            if user_msg.role != "user" or assistant_msg.role != "assistant":
                del history.turns[0]
                continue

            match = self._anchor_detector.detect(user_msg.content)
            if match.is_anchor:
                history.anchors.extend([user_msg, assistant_msg])
            else:
                evicted_for_summary.extend([user_msg, assistant_msg])
            del history.turns[0:2]

        if evicted_for_summary:
            history.summary = self._summarizer.summarize(
                previous_summary=history.summary,
                evicted=evicted_for_summary,
            )

        logger.info(
            "history_compressed",
            extra={
                "anchors_count": len(history.anchors),
                "recent_messages": len(history.turns),
                "summary_chars": len(history.summary or ""),
            },
        )
