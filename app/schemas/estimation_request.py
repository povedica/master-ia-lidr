"""Structured estimation request (guided form) — HTTP contract for /estimate endpoints."""

from __future__ import annotations

import base64
import binascii
import re
from enum import StrEnum
from typing import Self

from pydantic import BaseModel, Field, field_validator, model_validator

# --- Attachment limits (documented in README / docs/technical) ---
_ATTACHMENT_ALLOWED_TYPES: frozenset[str] = frozenset(
    {"text/plain", "text/markdown", "application/pdf"}
)
_MAX_ATTACHMENTS = 3
_MAX_ATTACHMENT_BYTES = 256 * 1024
_MAX_ATTACHMENTS_TOTAL_BYTES = 512 * 1024

# --- Text limits ---
_PROJECT_NAME_MAX = 120
_PROJECT_SUMMARY_MIN = 20
_PROJECT_SUMMARY_MAX = 200
_PROJECT_DESCRIPTION_MIN = 100
_PROJECT_DESCRIPTION_MAX = 24_000
_INDUSTRY_OTHER_MAX = 80
_TARGET_AUDIENCE_OTHER_MAX = 200


class ProjectType(StrEnum):
    web_saas = "web_saas"
    web_marketing_site = "web_marketing_site"
    mobile_app = "mobile_app"
    internal_tool = "internal_tool"
    data_pipeline_etl = "data_pipeline_etl"
    api_platform = "api_platform"
    desktop_app = "desktop_app"
    extension_plugin = "extension_plugin"
    migration_modernization = "migration_modernization"
    other = "other"


class Industry(StrEnum):
    fintech = "fintech"
    health = "health"
    ecommerce = "ecommerce"
    education = "education"
    public_sector = "public_sector"
    industrial = "industrial"
    generic_b2b = "generic_b2b"
    other = "other"


class TargetAudience(StrEnum):
    b2c_consumers = "b2c_consumers"
    b2b_smb = "b2b_smb"
    b2b_enterprise = "b2b_enterprise"
    internal_employees = "internal_employees"
    mixed = "mixed"
    other = "other"


class DetailLevel(StrEnum):
    summary = "summary"
    medium = "medium"
    detailed = "detailed"


class OutputFormat(StrEnum):
    phases_table = "phases_table"
    line_items = "line_items"
    narrative = "narrative"


_FILENAME_UNSAFE = re.compile(r"[\\/]|\.{2}")


class Attachment(BaseModel):
    """Inline attachment: base64 body (JSON-friendly; see README for limits)."""

    filename: str = Field(..., max_length=255, description="Original file name; no path segments.")
    content_type: str = Field(..., max_length=120)
    content_base64: str = Field(..., min_length=1, description="Standard base64 (no data: URL prefix).")

    @field_validator("filename")
    @classmethod
    def filename_rules(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("filename must not be empty")
        if _FILENAME_UNSAFE.search(stripped):
            raise ValueError("filename must not contain path segments or '..'")
        return stripped

    @field_validator("content_type")
    @classmethod
    def content_type_normalized(cls, value: str) -> str:
        key = value.strip().lower()
        if key not in _ATTACHMENT_ALLOWED_TYPES:
            allowed = ", ".join(sorted(_ATTACHMENT_ALLOWED_TYPES))
            raise ValueError(f"content_type must be one of: {allowed}")
        return key

    @model_validator(mode="after")
    def decode_and_size(self) -> Self:
        raw = _decode_base64_payload(self.content_base64)
        if len(raw) > _MAX_ATTACHMENT_BYTES:
            raise ValueError(
                f"decoded attachment exceeds {_MAX_ATTACHMENT_BYTES} bytes (limit for estimador-cag)"
            )
        return self


def _decode_base64_payload(blob: str) -> bytes:
    cleaned = "".join(blob.split())
    try:
        return base64.b64decode(cleaned, validate=True)
    except binascii.Error as exc:
        raise ValueError("content_base64 is not valid base64") from exc


def attachment_decoded_size(att: Attachment) -> int:
    """Return decoded byte length (attachments are small; re-decode is acceptable)."""

    return len(_decode_base64_payload(att.content_base64))


class EstimationRequest(BaseModel):
    """Inbound guided form payload for estimation (replaces legacy transcription-only body)."""

    project_name: str | None = Field(default=None, max_length=_PROJECT_NAME_MAX)
    project_summary: str = Field(..., min_length=1, max_length=_PROJECT_SUMMARY_MAX)
    project_type: ProjectType
    target_audience: TargetAudience
    target_audience_other: str | None = Field(default=None, max_length=_TARGET_AUDIENCE_OTHER_MAX)
    industry: Industry | None = None
    industry_other: str | None = Field(default=None, max_length=_INDUSTRY_OTHER_MAX)
    project_description: str = Field(..., min_length=1, max_length=_PROJECT_DESCRIPTION_MAX)
    detail_level: DetailLevel
    output_format: OutputFormat
    attachments: list[Attachment] = Field(default_factory=list, max_length=_MAX_ATTACHMENTS)
    preprocessing: str = Field(
        default="none",
        description="Input preprocessing: none | inline_cleaning | two_phase.",
    )
    evaluate: bool = Field(
        default=True,
        description="When true, run structure evaluation on the JSON estimate response path.",
    )

    @field_validator("project_name")
    @classmethod
    def strip_optional_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None

    @field_validator("project_summary")
    @classmethod
    def project_summary_trim_and_length(cls, value: str) -> str:
        stripped = value.strip()
        if len(stripped) < _PROJECT_SUMMARY_MIN:
            raise ValueError(f"project_summary must be at least {_PROJECT_SUMMARY_MIN} characters after trim")
        if len(stripped) > _PROJECT_SUMMARY_MAX:
            raise ValueError(f"project_summary must be at most {_PROJECT_SUMMARY_MAX} characters after trim")
        return stripped

    @field_validator("project_description")
    @classmethod
    def project_description_trim_and_length(cls, value: str) -> str:
        stripped = value.strip()
        if len(stripped) < _PROJECT_DESCRIPTION_MIN:
            raise ValueError(
                f"project_description must be at least {_PROJECT_DESCRIPTION_MIN} characters after trim"
            )
        if len(stripped) > _PROJECT_DESCRIPTION_MAX:
            raise ValueError(
                f"project_description must be at most {_PROJECT_DESCRIPTION_MAX} characters after trim"
            )
        return stripped

    @field_validator("industry_other")
    @classmethod
    def industry_other_trim(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None

    @field_validator("target_audience_other")
    @classmethod
    def target_audience_other_trim(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None

    @field_validator("preprocessing")
    @classmethod
    def normalize_preprocessing(cls, value: str) -> str:
        allowed = {"none", "inline_cleaning", "two_phase"}
        key = value.strip().lower()
        if key not in allowed:
            raise ValueError(f"preprocessing must be one of {sorted(allowed)}")
        return key

    @model_validator(mode="after")
    def industry_other_required(self) -> Self:
        if self.industry == Industry.other:
            if not self.industry_other:
                raise ValueError("industry_other is required when industry is 'other'")
        return self

    @model_validator(mode="after")
    def target_audience_other_required(self) -> Self:
        if self.target_audience == TargetAudience.other:
            if not self.target_audience_other:
                raise ValueError("target_audience_other is required when target_audience is 'other'")
        return self

    @model_validator(mode="after")
    def attachments_count_and_total(self) -> Self:
        if len(self.attachments) > _MAX_ATTACHMENTS:
            raise ValueError(f"at most {_MAX_ATTACHMENTS} attachments are allowed")
        total = 0
        for att in self.attachments:
            total += attachment_decoded_size(att)
        if total > _MAX_ATTACHMENTS_TOTAL_BYTES:
            raise ValueError(
                f"total decoded attachment size exceeds {_MAX_ATTACHMENTS_TOTAL_BYTES} bytes"
            )
        return self
