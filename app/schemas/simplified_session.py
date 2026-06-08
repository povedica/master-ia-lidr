"""Simplified session estimate HTTP contract (transcript-centered submit)."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Self

from pydantic import BaseModel, Field, field_validator, model_validator

from app.schemas.estimation_request import (
    Industry,
    ProjectType,
    TargetAudience,
    _ATTACHMENT_ALLOWED_TYPES,
    _FILENAME_UNSAFE,
    _MAX_ATTACHMENT_BYTES,
    _MAX_ATTACHMENTS,
    _MAX_ATTACHMENTS_TOTAL_BYTES,
    _decode_base64_payload,
)
from app.services.sessions import DerivedProjectMetadata

_PROJECT_NAME_MAX = 120
_ONE_LINE_SUMMARY_MAX = 200
_TRANSCRIPT_MIN = 80
_TRANSCRIPT_MAX = 24_000
_ADDITIONAL_EXTRA_INFO_MAX = 4_000


class AttachmentRef(BaseModel):
    """Attachment reference; inline base64 is transitional until a dedicated upload API exists."""

    file_id: str = Field(..., min_length=1, max_length=64)
    name: str = Field(..., max_length=255, description="Original file name; no path segments.")
    mime_type: str = Field(..., max_length=120)
    content_base64: str | None = Field(
        default=None,
        description="Optional inline body (base64). Required when the file is not pre-registered.",
    )

    @field_validator("name")
    @classmethod
    def name_rules(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("name must not be empty")
        if _FILENAME_UNSAFE.search(stripped):
            raise ValueError("name must not contain path segments or '..'")
        return stripped

    @field_validator("mime_type")
    @classmethod
    def mime_type_normalized(cls, value: str) -> str:
        key = value.strip().lower()
        if key not in _ATTACHMENT_ALLOWED_TYPES:
            allowed = ", ".join(sorted(_ATTACHMENT_ALLOWED_TYPES))
            raise ValueError(f"mime_type must be one of: {allowed}")
        return key

    @model_validator(mode="after")
    def validate_inline_size(self) -> Self:
        if self.content_base64 is None:
            return self
        raw = _decode_base64_payload(self.content_base64)
        if len(raw) > _MAX_ATTACHMENT_BYTES:
            raise ValueError(
                f"decoded attachment exceeds {_MAX_ATTACHMENT_BYTES} bytes (limit for estimador-cag)"
            )
        return self

    def decoded_bytes(self) -> bytes | None:
        if self.content_base64 is None:
            return None
        return _decode_base64_payload(self.content_base64)


class SessionEstimateRequest(BaseModel):
    """Simplified session submit centered on a free-form transcript."""

    project_name: str | None = Field(default=None, max_length=_PROJECT_NAME_MAX)
    one_line_summary: str | None = Field(default=None, max_length=_ONE_LINE_SUMMARY_MAX)
    project_type: ProjectType | None = None
    transcript: str = Field(
        ...,
        min_length=_TRANSCRIPT_MIN,
        max_length=_TRANSCRIPT_MAX,
        description="Primary narrative (discovery notes, requirements, assumptions).",
    )
    target_audience: TargetAudience | None = None
    industry: Industry | None = None
    additional_extra_info: str | None = Field(default=None, max_length=_ADDITIONAL_EXTRA_INFO_MAX)
    attachments: list[AttachmentRef] = Field(default_factory=list, max_length=_MAX_ATTACHMENTS)
    orchestration: Literal["default", "acb", "single_pass"] | None = Field(
        default=None,
        description="Optional ACB override: default follows settings; acb forces on; single_pass disables.",
    )

    @field_validator("project_name", "transcript", "one_line_summary", "additional_extra_info")
    @classmethod
    def strip_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        return stripped if stripped else None

    @field_validator("transcript")
    @classmethod
    def transcript_not_empty(cls, value: str | None) -> str:
        if not value:
            raise ValueError("transcript must not be empty")
        if len(value) < _TRANSCRIPT_MIN:
            raise ValueError(f"transcript must be at least {_TRANSCRIPT_MIN} characters after trim")
        return value

    @model_validator(mode="after")
    def attachment_totals(self) -> Self:
        if not self.attachments:
            return self
        total = 0
        for ref in self.attachments:
            raw = ref.decoded_bytes()
            if raw is not None:
                total += len(raw)
        if total > _MAX_ATTACHMENTS_TOTAL_BYTES:
            raise ValueError(
                f"total decoded attachments exceed {_MAX_ATTACHMENTS_TOTAL_BYTES} bytes"
            )
        return self


class AttachmentProcessingStatus(BaseModel):
    """Per-attachment resolution outcome for the response envelope."""

    file_id: str
    name: str
    mime_type: str
    status: str = Field(description="processed | failed | unsupported | skipped")
    message: str | None = None


class SessionEstimateResponse(BaseModel):
    """Structured session estimate result for the simplified UI."""

    session_id: str
    input_payload: dict[str, Any]
    project_metadata: DerivedProjectMetadata
    estimate: dict[str, Any]
    warnings: list[str] = Field(default_factory=list)
    attachments: list[AttachmentProcessingStatus] = Field(default_factory=list)


class SessionListItem(BaseModel):
    """Summary row for session history sidebar."""

    session_id: str
    label: str
    updated_at: datetime
    submit_count: int = 0


class SessionListResponse(BaseModel):
    """List of in-memory sessions (newest first, bounded window)."""

    sessions: list[SessionListItem] = Field(default_factory=list)


class SessionDetailResponse(BaseModel):
    """Session snapshot for restoring form, metadata, and last estimate in the UI."""

    session_id: str
    input_payload: dict[str, Any] | None = None
    project_metadata: dict[str, Any] | None = None
    estimate: dict[str, Any] | None = None
    warnings: list[str] = Field(default_factory=list)
    attachments: list[AttachmentProcessingStatus] = Field(default_factory=list)
    submit_count: int = 0
    last_turn_observation: dict[str, Any] | None = None
