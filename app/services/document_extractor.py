"""Extract plain text from uploaded session attachments."""

from __future__ import annotations

import base64
import binascii
import io
from dataclasses import dataclass

from docx import Document
from pypdf import PdfReader

from app.config import Settings
from app.schemas.estimation_request import Attachment
from app.services.attachment_errors import (
    AttachmentTooLargeError,
    ExtractionFailedError,
    UnsupportedFormatError,
    UnsupportedMimeTypeError,
)

_MS_WORD_LEGACY = "application/msword"
_DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


@dataclass(frozen=True)
class ExtractedAttachment:
    """Plain-text extraction result for one attachment."""

    filename: str
    content_type: str
    text: str


class DocumentTextExtractor:
    """Decode and extract text from supported attachment MIME types."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._allowed = frozenset(settings.allowed_attachment_mime_types_list())

    def extract_all(self, attachments: list[Attachment]) -> list[ExtractedAttachment]:
        """Extract text from each attachment; raises ``AttachmentError`` on failure."""

        results: list[ExtractedAttachment] = []
        for att in attachments:
            results.append(self.extract_one(att))
        return results

    def extract_one(self, attachment: Attachment) -> ExtractedAttachment:
        mime = attachment.content_type.strip().lower()
        if mime not in self._allowed:
            raise UnsupportedMimeTypeError(mime)

        raw = self._decode_bytes(attachment.content_base64)
        limit = self._settings.max_attachment_size_bytes
        if len(raw) > limit:
            raise AttachmentTooLargeError(
                filename=attachment.filename,
                size_bytes=len(raw),
                limit_bytes=limit,
            )

        if mime == _MS_WORD_LEGACY:
            raise UnsupportedFormatError(
                filename=attachment.filename,
                hint="Legacy .doc is not supported; convert to .docx.",
            )

        try:
            text = self._extract_text(mime, raw)
        except AttachmentTooLargeError:
            raise
        except UnsupportedFormatError:
            raise
        except UnsupportedMimeTypeError:
            raise
        except Exception as exc:
            raise ExtractionFailedError(
                filename=attachment.filename,
                reason=str(exc),
            ) from exc

        return ExtractedAttachment(
            filename=attachment.filename,
            content_type=mime,
            text=text.strip(),
        )

    def _decode_bytes(self, content_base64: str) -> bytes:
        cleaned = "".join(content_base64.split())
        try:
            return base64.b64decode(cleaned, validate=True)
        except binascii.Error as exc:
            raise ExtractionFailedError(
                filename="attachment",
                reason="invalid base64 payload",
            ) from exc

    def _extract_text(self, mime: str, raw: bytes) -> str:
        if mime in {"text/plain", "text/markdown"}:
            return raw.decode("utf-8", errors="replace")
        if mime == "application/pdf":
            return self._extract_pdf(raw)
        if mime == _DOCX:
            return self._extract_docx(raw)
        raise UnsupportedMimeTypeError(mime)

    def _extract_pdf(self, raw: bytes) -> str:
        reader = PdfReader(io.BytesIO(raw))
        parts: list[str] = []
        for index, page in enumerate(reader.pages, start=1):
            page_text = page.extract_text() or ""
            parts.append(f"--- Page {index} ---\n{page_text.strip()}")
        return "\n\n".join(parts)

    def _extract_docx(self, raw: bytes) -> str:
        document = Document(io.BytesIO(raw))
        paragraphs = [p.text.strip() for p in document.paragraphs if p.text.strip()]
        return "\n".join(paragraphs)
