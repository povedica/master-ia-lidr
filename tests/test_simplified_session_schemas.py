"""Unit tests for simplified session estimate request/response schemas."""

from __future__ import annotations

import base64

import pytest
from pydantic import ValidationError

from app.schemas.estimation_request import Industry, ProjectType, TargetAudience
from app.schemas.simplified_session import (
    AttachmentRef,
    SessionEstimateRequest,
    SessionEstimateResponse,
)
from app.services.sessions import DerivedProjectMetadata


def _minimal_request_dict(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "project_name": "Acme Portal",
        "project_type": ProjectType.web_saas.value,
        "transcript": "A" * 80,
        "target_audience": TargetAudience.b2b_smb.value,
    }
    payload.update(overrides)
    return payload


def test_session_estimate_request_requires_core_fields() -> None:
    request = SessionEstimateRequest(**_minimal_request_dict())
    assert request.project_name == "Acme Portal"
    assert request.transcript == "A" * 80


def test_session_estimate_request_rejects_short_transcript() -> None:
    with pytest.raises(ValidationError, match="transcript"):
        SessionEstimateRequest(**_minimal_request_dict(transcript="too short"))


def test_session_estimate_request_trims_project_name() -> None:
    request = SessionEstimateRequest(**_minimal_request_dict(project_name="  Trimmed  "))
    assert request.project_name == "Trimmed"


def test_attachment_ref_accepts_inline_base64() -> None:
    raw = b"hello world"
    ref = AttachmentRef(
        file_id="f-1",
        name="notes.txt",
        mime_type="text/plain",
        content_base64=base64.b64encode(raw).decode(),
    )
    assert ref.decoded_bytes() == raw


def test_session_estimate_response_envelope_fields() -> None:
    metadata = DerivedProjectMetadata(
        project_name="Acme",
        project_type=ProjectType.web_saas,
        target_audience=TargetAudience.b2b_smb,
        summary="Short summary",
    )
    response = SessionEstimateResponse(
        session_id="sess-1",
        input_payload=_minimal_request_dict(),
        project_metadata=metadata,
        estimate={"result": {"title": "T", "summary": "S" * 25}},
        warnings=["industry not provided"],
        attachments=[],
    )
    assert response.session_id == "sess-1"
    assert response.warnings == ["industry not provided"]
