"""Minimal attachment payloads for integration tests."""

from __future__ import annotations

import base64
from io import BytesIO
from typing import Any


def _pdf_escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def minimal_pdf_with_text(text: str) -> bytes:
    """Build a one-page PDF with Helvetica text extractable by ``pypdf``."""

    safe = _pdf_escape(text)
    stream = f"BT /F1 12 Tf 72 720 Td ({safe}) Tj ET"
    stream_b = stream.encode("latin-1", errors="replace")
    buf = BytesIO()

    def write(data: bytes) -> None:
        buf.write(data)

    offsets: list[int] = []

    def mark_object() -> None:
        offsets.append(buf.tell())

    write(b"%PDF-1.4\n")
    mark_object()
    write(b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n")
    mark_object()
    write(b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n")
    mark_object()
    write(
        b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >> >>\nendobj\n"
    )
    mark_object()
    write(f"4 0 obj\n<< /Length {len(stream_b)} >>\nstream\n".encode())
    write(stream_b)
    write(b"\nendstream\nendobj\n")
    mark_object()
    write(b"5 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj\n")
    xref_start = buf.tell()
    write(b"xref\n0 6\n0000000000 65535 f \n")
    for offset in offsets:
        write(f"{offset:010d} 00000 n \n".encode())
    write(b"trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n")
    write(f"{xref_start}\n".encode())
    write(b"%%EOF\n")
    return buf.getvalue()


def attachment_ref(*, name: str, mime_type: str, raw: bytes, file_id: str = "f1") -> dict[str, Any]:
    encoded = base64.b64encode(raw).decode("ascii")
    return {
        "file_id": file_id,
        "name": name,
        "mime_type": mime_type,
        "content_base64": encoded,
    }


def redis_marker_pdf_attachment_ref() -> dict[str, Any]:
    text = "Project addendum: ATTACH_MARKER:USE_REDIS must be reflected in the estimate."
    return attachment_ref(
        name="redis_addendum.pdf",
        mime_type="application/pdf",
        raw=minimal_pdf_with_text(text),
    )
