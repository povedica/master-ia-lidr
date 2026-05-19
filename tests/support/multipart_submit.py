"""Helpers for multipart session estimate integration tests."""

from __future__ import annotations

import io
from typing import Any


def multipart_submit_fields(**overrides: str | None) -> dict[str, str]:
    """Default form fields for a valid first submit (transcript >= 80 chars)."""

    defaults: dict[str, str] = {
        "project_name": "Acme Portal",
        "project_type": "web_saas",
        "target_audience": "b2b_smb",
        "transcript": (
            "We need a B2B SaaS customer portal for Acme Corp. "
            "Stack: Python, FastAPI, PostgreSQL. Team of 4 developers. "
            "Scope: authentication, dashboard, billing integration."
        ),
    }
    for key, value in overrides.items():
        if value is None:
            defaults.pop(key, None)
        else:
            defaults[key] = value
    return defaults


def multipart_attachment_file(
    *,
    name: str,
    content: bytes,
    content_type: str,
) -> tuple[str, tuple[str, io.BytesIO, str]]:
    """Single file tuple for httpx ``files=`` (repeated field name ``attachments``)."""

    return ("attachments", (name, io.BytesIO(content), content_type))


def force_multipart_encoding() -> list[tuple[str, tuple[str, io.BytesIO, str]]]:
    """Force ``multipart/form-data`` when httpx would otherwise use urlencoded ``data=`` only."""

    return [("attachments", ("", io.BytesIO(b""), "text/plain"))]


def turn_2_multipart_fields() -> dict[str, str]:
    """Second-turn payload omitting project_name (FR-05)."""

    return multipart_submit_fields(
        project_name=None,
        transcript=(
            "Same Acme Portal project — add Redis caching for session tokens "
            "and keep the existing PostgreSQL datastore."
        ),
    )
