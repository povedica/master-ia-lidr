"""Unit tests for minimal PDF fixture generation."""

from __future__ import annotations

from io import BytesIO

from pypdf import PdfReader

from tests.fixtures.attachment_bytes import minimal_pdf_with_text


def test_minimal_pdf_with_text_is_extractable() -> None:
    marker = "ATTACH_MARKER:USE_REDIS"
    raw = minimal_pdf_with_text(f"Project addendum: {marker} for tests.")
    reader = PdfReader(BytesIO(raw))
    extracted = "\n".join(page.extract_text() or "" for page in reader.pages)
    assert marker in extracted
