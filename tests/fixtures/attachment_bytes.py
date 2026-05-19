"""Minimal attachment payloads for integration tests."""

from __future__ import annotations

import base64
from typing import Any


def minimal_text_attachment_bytes(text: str) -> bytes:
    return text.encode("utf-8")


def attachment_ref(*, name: str, mime_type: str, raw: bytes, file_id: str = "f1") -> dict[str, Any]:
    encoded = base64.b64encode(raw).decode("ascii")
    return {
        "file_id": file_id,
        "name": name,
        "mime_type": mime_type,
        "content_base64": encoded,
    }


def redis_marker_attachment_ref() -> dict[str, Any]:
    text = "Project addendum: ATTACH_MARKER:USE_REDIS must be reflected in the estimate."
    return attachment_ref(
        name="redis_addendum.txt",
        mime_type="text/plain",
        raw=minimal_text_attachment_bytes(text),
    )
