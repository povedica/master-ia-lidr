"""Validators for ``EstimationRequest`` and ``Attachment``."""

from __future__ import annotations

import base64

import pytest
from pydantic import ValidationError

from app.schemas.estimation_request import (
    Attachment,
    EstimationRequest,
    Industry,
    ProjectType,
    TargetAudience,
)


def _valid_kwargs() -> dict[str, object]:
    return {
        "project_summary": "Short summary for tests with enough chars.",
        "project_type": ProjectType.web_saas,
        "target_audience": TargetAudience.b2b_smb,
        "project_description": "x" * 100,
        "detail_level": "medium",
        "output_format": "phases_table",
    }


def test_industry_other_required_when_industry_other() -> None:
    with pytest.raises(ValidationError):
        EstimationRequest(
            **_valid_kwargs(),
            industry=Industry.other,
            industry_other=None,
        )


def test_target_audience_other_required() -> None:
    with pytest.raises(ValidationError):
        EstimationRequest(
            **{
                **_valid_kwargs(),
                "target_audience": TargetAudience.other,
                "target_audience_other": None,
            }
        )


def test_attachment_rejects_invalid_base64() -> None:
    with pytest.raises(ValidationError):
        Attachment(
            filename="notes.txt",
            content_type="text/plain",
            content_base64="@@@not-base64@@@",
        )


def test_attachment_rejects_disallowed_content_type() -> None:
    raw = base64.b64encode(b"hello").decode("ascii")
    with pytest.raises(ValidationError):
        Attachment(
            filename="notes.bin",
            content_type="application/octet-stream",
            content_base64=raw,
        )


def test_attachments_total_size_cap() -> None:
    chunk = b"x" * (200 * 1024)
    b64 = base64.b64encode(chunk).decode("ascii")
    att1 = Attachment(filename="a.txt", content_type="text/plain", content_base64=b64)
    att2 = Attachment(filename="b.txt", content_type="text/plain", content_base64=b64)
    att3 = Attachment(filename="c.txt", content_type="text/plain", content_base64=b64)
    with pytest.raises(ValidationError):
        EstimationRequest(
            **_valid_kwargs(),
            attachments=[att1, att2, att3],
        )
