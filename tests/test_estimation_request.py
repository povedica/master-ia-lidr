"""Validators for ``EstimationRequest`` and ``Attachment``."""

from __future__ import annotations

import base64
from datetime import date

import pytest
from pydantic import ValidationError

from app.schemas.estimation_request import (
    Attachment,
    DeliveryUrgency,
    EstimationRequest,
    Industry,
    IntegrationCategory,
    ProjectType,
    TargetAudience,
)


def _valid_kwargs() -> dict[str, object]:
    return {
        "project_summary": "Short summary for tests with enough chars.",
        "project_type": ProjectType.web_saas,
        "target_audience": TargetAudience.b2b_smb,
        "project_description": "x" * 100,
        "deliverables": ["One deliverable line here", "Second deliverable line ok", "Third deliverable line ok"],
        "delivery_urgency": DeliveryUrgency.standard,
        "data_sensitivity": "internal_business",
        "detail_level": "medium",
        "output_format": "phases_table",
    }


def test_deliverables_count_too_low_rejected() -> None:
    with pytest.raises(ValidationError):
        EstimationRequest(**{**_valid_kwargs(), "deliverables": ["a", "b"]})


def test_deliverables_item_too_long_rejected() -> None:
    long_line = "x" * 81
    with pytest.raises(ValidationError):
        EstimationRequest(
            **{
                **_valid_kwargs(),
                "deliverables": [long_line, "b" * 20, "c" * 20],
            }
        )


def test_target_date_required_for_fixed_date() -> None:
    with pytest.raises(ValidationError):
        EstimationRequest(
            **{
                **_valid_kwargs(),
                "delivery_urgency": DeliveryUrgency.fixed_date,
                "target_date": None,
            }
        )


def test_target_date_required_for_critical() -> None:
    with pytest.raises(ValidationError):
        EstimationRequest(
            **{
                **_valid_kwargs(),
                "delivery_urgency": DeliveryUrgency.critical,
                "target_date": None,
            }
        )


def test_target_date_allowed_for_fixed_date() -> None:
    req = EstimationRequest(
        **{
            **_valid_kwargs(),
            "delivery_urgency": DeliveryUrgency.fixed_date,
            "target_date": date(2026, 12, 31),
        }
    )
    assert req.target_date == date(2026, 12, 31)


def test_integration_none_mutually_exclusive() -> None:
    with pytest.raises(ValidationError):
        EstimationRequest(
            **_valid_kwargs(),
            integration_categories=[IntegrationCategory.none, IntegrationCategory.payments],
        )


def test_integration_none_normalizes_to_empty() -> None:
    req = EstimationRequest(
        **_valid_kwargs(),
        integration_categories=[IntegrationCategory.none],
    )
    assert req.integration_categories == []


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
