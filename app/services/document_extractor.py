"""Extract plain text from session attachment payloads."""

from __future__ import annotations

import io
from dataclasses import dataclass

from docx import Document
from pypdf import PdfReader

from app.config import Settings
from app.schemas.estimation_request import Attachment
from app.services.attachment_errors import AttachmentError

_TEXT_MIMES = frozenset({"text/plain", "text/markdown"})
_PDF_MIME = "application/pdf"
_DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
_DOC_MIME = "application/msword"


@dataclass(frozen=True)
class ExtractedAttachment:
    """Plain-text extraction result for one attachment."""

    filename: str
    mime_type: str
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
            raise AttachmentError(
                status_code=422,
                code="unsupported_mime_type",
                message=f"Unsupported attachment type: {mime}",
            )

        raw = self._decode_bytes(attachment.content_base64)
        limit = self._settings.max_attachment_size_bytes
        if len(raw) > limit:
            raise AttachmentError(
                status_code=413,
                code="attachment_too_large",
                message=f"Attachment {attachment.filename!r} exceeds size limit.",
            )

        if mime in _TEXT_MIMES:
            text = raw.decode("utf-8", errors="replace")
        elif mime == _PDF_MIME:
            text = self._extract_pdf(raw)
        elif mime == _DOCX_MIME:
            text = self._extract_docx(raw)
        elif mime == _DOC_MIME:
            raise AttachmentError(
                status_code=422,
                code="unsupported_legacy_doc",
                message="Legacy .doc files are unsupported; convert to .docx.",
            )
        else:
            raise AttachmentError(
                status_code=422,
                code="unsupported_mime_type",
                message=f"Unsupported attachment type: {mime}",
            )

        return ExtractedAttachment(
            filename=attachment.filename,
            mime_type=mime,
            text=text.strip(),
        )

    def _decode_bytes(self, content_base64: str) -> bytes:
        from app.schemas.estimation_request import _decode_base64_payload

        try:
            return _decode_base64_payload(content_base64)
        except ValueError as exc:
            raise AttachmentError(
                status_code=422,
                code="invalid_base64",
                message="Attachment body is not valid base64.",
            ) from exc

    def _extract_pdf(self, raw: bytes) -> str:
        try:
            reader = PdfReader(io.BytesIO(raw))
            pages = [page.extract_text() or "" for page in reader.pages]
            return "\n\n---\n\n".join(pages)
        except Exception as exc:
            raise AttachmentError(
                status_code=422,
                code="pdf_extract_failed",
                message="Could not extract text from PDF attachment.",
            ) from exc

    def _extract_docx(self, raw: bytes) -> str:
        try:
            document = Document(io.BytesIO(raw))
            return "\n".join(p.text for p in document.paragraphs if p.text.strip())
        except Exception as exc:
            raise AttachmentError(
                status_code=422,
                code="docx_extract_failed",
                message="Could not extract text from DOCX attachment.",
            ) from exc
