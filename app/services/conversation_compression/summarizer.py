"""Cumulative summarizer for evicted session turns (feature-064)."""

from __future__ import annotations

import logging
from typing import Callable

from app.services.sessions import ChatMessage

logger = logging.getLogger(__name__)

SummaryFn = Callable[[str | None, list[ChatMessage]], str]


class CumulativeSummarizer:
    def __init__(self, summarize_fn: SummaryFn | None = None) -> None:
        self._summarize_fn = summarize_fn or _default_summarize

    def summarize(self, *, previous_summary: str | None, evicted: list[ChatMessage]) -> str:
        if not evicted:
            return previous_summary or ""
        try:
            return self._summarize_fn(previous_summary, evicted)
        except Exception as exc:
            logger.warning(
                "summarizer_failed",
                extra={"error_type": type(exc).__name__},
            )
            return previous_summary or ""


def _default_summarize(previous_summary: str | None, evicted: list[ChatMessage]) -> str:
    lines = []
    if previous_summary:
        lines.append(previous_summary.strip())
    for message in evicted:
        lines.append(f"{message.role}: {message.content.strip()}")
    joined = "\n".join(line for line in lines if line)
    return joined[:4000]
