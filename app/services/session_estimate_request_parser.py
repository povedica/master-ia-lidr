"""Parse simplified session estimate submits from JSON or multipart form data."""

from __future__ import annotations

import logging

from fastapi import Request, UploadFile
from starlette.datastructures import FormData

from app.schemas.estimation_request import Industry, ProjectType, TargetAudience
from app.schemas.simplified_session import SessionEstimateRequest
from app.services.multipart_attachments import upload_files_to_attachment_refs

logger = logging.getLogger(__name__)


class SessionEstimateParseError(ValueError):
    """Deterministic client error while parsing a session estimate request."""

    def __init__(self, message: str, *, code: str = "invalid_session_submit") -> None:
        super().__init__(message)
        self.code = code


async def parse_session_estimate_request(request: Request) -> SessionEstimateRequest:
    """Build ``SessionEstimateRequest`` from JSON or multipart form data."""

    content_type = (request.headers.get("content-type") or "").lower()
    if content_type.startswith("multipart/form-data"):
        return await _parse_multipart_request(request)
    if content_type.startswith("application/json") or not content_type:
        try:
            payload = await request.json()
        except Exception as exc:
            raise SessionEstimateParseError("request body must be valid JSON") from exc
        return _validate_payload(payload)
    raise SessionEstimateParseError(
        "Content-Type must be application/json or multipart/form-data",
        code="unsupported_media_type",
    )


async def parse_multipart_form(form: FormData) -> SessionEstimateRequest:
    """Map multipart form fields and file parts to a session estimate request."""

    uploads = _collect_upload_files(form)
    attachment_refs = await upload_files_to_attachment_refs(uploads)

    payload: dict[str, object] = {
        "transcript": _required_form_text(form, "transcript"),
        "project_name": _optional_form_text(form, "project_name"),
        "one_line_summary": _optional_form_text(form, "one_line_summary"),
        "project_type": _optional_enum(form, "project_type", ProjectType),
        "target_audience": _optional_enum(form, "target_audience", TargetAudience),
        "industry": _optional_enum(form, "industry", Industry),
        "additional_extra_info": _optional_form_text(form, "additional_extra_info"),
        "attachments": attachment_refs,
    }
    return _validate_payload(payload)


async def _parse_multipart_request(request: Request) -> SessionEstimateRequest:
    try:
        form = await request.form()
    except Exception as exc:
        raise SessionEstimateParseError("could not read multipart form data") from exc
    return await parse_multipart_form(form)


def _validate_payload(payload: dict[str, object]) -> SessionEstimateRequest:
    return SessionEstimateRequest.model_validate(payload)


def _collect_upload_files(form: FormData) -> list[UploadFile]:
    uploads: list[UploadFile] = []
    for key, value in form.multi_items():
        if key != "attachments":
            continue
        if isinstance(value, UploadFile) and (value.filename or "").strip():
            uploads.append(value)
    return uploads


def _form_value(form: FormData, name: str) -> object | None:
    if name not in form:
        return None
    return form.get(name)


def _optional_form_text(form: FormData, name: str) -> str | None:
    value = _form_value(form, name)
    if value is None or isinstance(value, UploadFile):
        return None
    text = str(value).strip()
    return text or None


def _required_form_text(form: FormData, name: str) -> str:
    text = _optional_form_text(form, name)
    if not text:
        raise SessionEstimateParseError(f"{name} is required")
    return text


def _optional_enum(form: FormData, name: str, enum_type: type) -> object | None:
    text = _optional_form_text(form, name)
    if text is None:
        return None
    try:
        return enum_type(text)
    except ValueError as exc:
        raise SessionEstimateParseError(f"invalid value for {name}") from exc
