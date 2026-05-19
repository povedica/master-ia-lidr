"""Convert multipart uploads into simplified session ``AttachmentRef`` payloads."""

from __future__ import annotations

import base64

from fastapi import UploadFile

from app.schemas.estimation_request import (
    _ATTACHMENT_ALLOWED_TYPES,
    _FILENAME_UNSAFE,
    _MAX_ATTACHMENT_BYTES,
    _MAX_ATTACHMENTS,
    _MAX_ATTACHMENTS_TOTAL_BYTES,
)
from app.schemas.simplified_session import AttachmentRef
from app.services.attachment_errors import AttachmentError

_DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def _guess_mime_type(filename: str) -> str:
    lower = filename.lower()
    if lower.endswith(".pdf"):
        return "application/pdf"
    if lower.endswith(".md"):
        return "text/markdown"
    if lower.endswith(".docx"):
        return _DOCX_MIME
    return "text/plain"


def _resolve_upload_mime(upload: UploadFile) -> str:
    raw = (upload.content_type or "").split(";")[0].strip().lower()
    if raw and raw not in {"application/octet-stream"}:
        return raw
    return _guess_mime_type(upload.filename or "")


async def upload_files_to_attachment_refs(files: list[UploadFile]) -> list[AttachmentRef]:
    """Read uploads, enforce limits, and map to inline base64 attachment refs."""

    if len(files) > _MAX_ATTACHMENTS:
        raise AttachmentError(
            status_code=422,
            code="too_many_attachments",
            message=f"at most {_MAX_ATTACHMENTS} attachments are allowed",
        )

    refs: list[AttachmentRef] = []
    total_bytes = 0
    for index, upload in enumerate(files):
        filename = (upload.filename or "").strip()
        if not filename:
            continue
        if _FILENAME_UNSAFE.search(filename):
            raise AttachmentError(
                status_code=422,
                code="invalid_attachment_name",
                message="attachment name must not contain path segments or '..'",
            )

        mime_type = _resolve_upload_mime(upload)
        if mime_type not in _ATTACHMENT_ALLOWED_TYPES:
            allowed = ", ".join(sorted(_ATTACHMENT_ALLOWED_TYPES))
            raise AttachmentError(
                status_code=422,
                code="unsupported_mime_type",
                message=f"mime_type must be one of: {allowed}",
            )

        raw = await upload.read()
        if len(raw) > _MAX_ATTACHMENT_BYTES:
            raise AttachmentError(
                status_code=413,
                code="attachment_too_large",
                message=f"decoded attachment exceeds {_MAX_ATTACHMENT_BYTES} bytes (limit for estimador-cag)",
            )
        total_bytes += len(raw)
        if total_bytes > _MAX_ATTACHMENTS_TOTAL_BYTES:
            raise AttachmentError(
                status_code=422,
                code="attachments_total_too_large",
                message=f"total decoded attachments exceed {_MAX_ATTACHMENTS_TOTAL_BYTES} bytes",
            )

        refs.append(
            AttachmentRef(
                file_id=f"upload-{index}",
                name=filename,
                mime_type=mime_type,
                content_base64=base64.b64encode(raw).decode("ascii"),
            )
        )

    return refs
