"""Unit tests for ``DocumentTextExtractor``."""

from __future__ import annotations

import base64
import io

import pytest
from docx import Document

from app.config import Settings
from app.schemas.estimation_request import Attachment
from app.services.attachment_errors import (
    AttachmentTooLargeError,
    UnsupportedFormatError,
    UnsupportedMimeTypeError,
)
from app.services.document_extractor import DocumentTextExtractor


def _settings(**kwargs: object) -> Settings:
    return Settings(openai_api_key="test", **kwargs)  # type: ignore[arg-type]


def _att(filename: str, mime: str, raw: bytes) -> Attachment:
    return Attachment(
        filename=filename,
        content_type=mime,
        content_base64=base64.b64encode(raw).decode("ascii"),
    )


def test_extract_plain_text() -> None:
    extractor = DocumentTextExtractor(_settings())
    result = extractor.extract_one(_att("notes.txt", "text/plain", b"Hello spec text."))
    assert result.text == "Hello spec text."


def test_extract_docx_paragraphs() -> None:
    buffer = io.BytesIO()
    doc = Document()
    doc.add_paragraph("First paragraph from docx.")
    doc.save(buffer)
    raw = buffer.getvalue()

    extractor = DocumentTextExtractor(_settings())
    result = extractor.extract_one(
        _att(
            "spec.docx",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            raw,
        )
    )
    assert "First paragraph from docx." in result.text


def test_unsupported_mime_raises() -> None:
    extractor = DocumentTextExtractor(_settings())
    att = Attachment.model_construct(
        filename="data.bin",
        content_type="application/octet-stream",
        content_base64=base64.b64encode(b"x").decode("ascii"),
    )
    with pytest.raises(UnsupportedMimeTypeError):
        extractor.extract_one(att)


def test_legacy_doc_raises_with_hint() -> None:
    extractor = DocumentTextExtractor(
        _settings(
            allowed_attachment_mime_types=(
                "text/plain,application/msword,application/pdf"
            ),
        )
    )
    att = Attachment.model_construct(
        filename="old.doc",
        content_type="application/msword",
        content_base64=base64.b64encode(b"fake").decode("ascii"),
    )
    with pytest.raises(UnsupportedFormatError) as exc_info:
        extractor.extract_one(att)
    assert "docx" in exc_info.value.message.lower()


def test_oversize_attachment_raises_413() -> None:
    extractor = DocumentTextExtractor(_settings(max_attachment_size_bytes=100))
    with pytest.raises(AttachmentTooLargeError):
        extractor.extract_one(_att("big.txt", "text/plain", b"x" * 200))
