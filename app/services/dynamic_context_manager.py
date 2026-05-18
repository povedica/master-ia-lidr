"""Build bounded external-context blocks for session user prompts."""

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

        if not extracted:
            return ""

        parts: list[str] = []
        for item in extracted:
            body = item.text
            if not body:
                continue
            parts.append(
                f'<attachment filename="{item.filename}">\n{body}\n</attachment>'
            )
        if not parts:
            return ""

        combined = "\n".join(parts)
        block = f"<attachments>\n{combined}\n</attachments>"
        return self._apply_budget(block)

    def _apply_budget(self, block: str) -> str:
        if len(block) <= self._max_chars:
            return block
        keep = self._max_chars - len(_TRUNCATION_MARKER)
        if keep < 0:
            keep = 0
        return block[:keep] + _TRUNCATION_MARKER
