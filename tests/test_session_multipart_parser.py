"""Unit tests for multipart session estimate request parsing."""

from __future__ import annotations

import io

import pytest
from fastapi import UploadFile
from starlette.datastructures import FormData, Headers

from app.services.multipart_attachments import upload_files_to_attachment_refs
from app.services.session_estimate_request_parser import (
    SessionEstimateParseError,
    parse_multipart_form,
)


def _text_upload(
    *,
    name: str,
    content: bytes,
    content_type: str = "text/plain",
) -> UploadFile:
    return UploadFile(
        filename=name,
        file=io.BytesIO(content),
        headers=Headers({"content-type": content_type}),
    )


@pytest.mark.asyncio
async def test_upload_files_to_attachment_refs_encodes_base64() -> None:
    raw = b"ATTACH_MARKER:USE_REDIS"
    refs = await upload_files_to_attachment_refs(
        [_text_upload(name="notes.txt", content=raw)],
    )
    assert len(refs) == 1
    assert refs[0].file_id == "upload-0"
    assert refs[0].name == "notes.txt"
    assert refs[0].mime_type == "text/plain"
    assert refs[0].decoded_bytes() == raw


@pytest.mark.asyncio
async def test_upload_files_rejects_unsupported_mime() -> None:
    from app.services.attachment_errors import AttachmentError

    upload = UploadFile(
        filename="image.png",
        file=io.BytesIO(b"\x89PNG"),
        headers=Headers({"content-type": "image/png"}),
    )
    with pytest.raises(AttachmentError, match="mime_type"):
        await upload_files_to_attachment_refs([upload])


@pytest.mark.asyncio
async def test_parse_multipart_form_builds_session_request() -> None:
    transcript = "Discovery notes for multipart parser test. " * 3
    form = FormData(
        [
            ("transcript", transcript),
            ("project_name", "Multipart Portal"),
            ("project_type", "web_saas"),
            ("target_audience", "b2b_smb"),
            ("attachments", _text_upload(name="notes.txt", content=b"extra context")),
        ]
    )
    request = await parse_multipart_form(form)
    assert request.project_name == "Multipart Portal"
    assert request.transcript == transcript.strip()
    assert len(request.attachments) == 1
    assert request.attachments[0].name == "notes.txt"


@pytest.mark.asyncio
async def test_parse_multipart_form_requires_transcript() -> None:
    form = FormData(
        [
            ("project_name", "Portal"),
            ("project_type", "web_saas"),
            ("target_audience", "b2b_smb"),
        ]
    )
    with pytest.raises(SessionEstimateParseError, match="transcript"):
        await parse_multipart_form(form)
