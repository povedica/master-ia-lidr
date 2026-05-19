"""Bounded attachment text blocks for prompt injection."""

from __future__ import annotations

from app.config import Settings
from app.services.document_extractor import ExtractedAttachment

_TRUNCATION_MARKER = "\n\n[... attachment text truncated to context budget ...]"


class DynamicContextManager:
    """Compose delimited attachment text for injection into the user prompt."""

    def __init__(self, settings: Settings) -> None:
        self._max_chars = settings.max_attachment_context_chars

    def build_context_block(self, extracted: list[ExtractedAttachment]) -> str:
        """Return an ``<attachments>`` block or empty string when there is no text."""

        parts: list[str] = []
        remaining = self._max_chars
        for item in extracted:
            body = item.text.strip()
            if not body:
                continue
            if len(body) > remaining:
                body = body[:remaining] + _TRUNCATION_MARKER
                remaining = 0
            else:
                remaining -= len(body)
            parts.append(
                f'<attachment filename="{item.filename}">\n{body}\n</attachment>'
            )
            if remaining <= 0:
                break

        if not parts:
            return ""
        combined = "\n\n".join(parts)
        return f"<attachments>\n{combined}\n</attachments>"
