"""Structured estimation request (guided form) — HTTP contract for /estimate endpoints."""

from __future__ import annotations

import base64
import binascii
import re
from datetime import date
from enum import StrEnum
from typing import Self

from pydantic import BaseModel, Field, field_validator, model_validator

# --- Attachment limits (documented in README / docs/technical) ---
_ATTACHMENT_ALLOWED_TYPES: frozenset[str] = frozenset(
    {
        "text/plain",
        "text/markdown",
        "application/pdf",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    }
)
_MAX_ATTACHMENTS = 3
_MAX_ATTACHMENT_BYTES = 10_485_760  # 10 MB per decoded file
_MAX_ATTACHMENTS_TOTAL_BYTES = 31_457_280  # 3 × 10 MB

# --- Text limits ---
_PROJECT_NAME_MAX = 120
_PROJECT_SUMMARY_MIN = 20
_PROJECT_SUMMARY_MAX = 200
_PROJECT_DESCRIPTION_MIN = 100
_PROJECT_DESCRIPTION_MAX = 24_000
_DELIVERABLE_ITEM_MAX = 80
_DELIVERABLES_MIN = 3
_DELIVERABLES_MAX = 8
_OUT_OF_SCOPE_MAX_ITEMS = 5
_INTEGRATION_CUSTOM_MAX_ITEMS = 3
_INTEGRATION_CUSTOM_MIN_LEN = 20
_INTEGRATION_CUSTOM_MAX_LEN = 300
_EXTERNAL_DEP_MAX_ITEMS = 3
_EXTERNAL_DEP_MAX_LEN = 100
_HOSTING_NOTES_MAX = 200
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


class DeliveryUrgency(StrEnum):
    flexible = "flexible"
    standard = "standard"
    fixed_date = "fixed_date"
    critical = "critical"


class DeliveryApproach(StrEnum):
    mvp_then_iterate = "mvp_then_iterate"
    single_release = "single_release"
    phased_roadmap = "phased_roadmap"
    unknown = "unknown"


class DataSensitivity(StrEnum):
    public_only = "public_only"
    internal_business = "internal_business"
    pii_light = "pii_light"
    pii_heavy = "pii_heavy"
    regulated_unknown = "regulated_unknown"


class IntegrationCategory(StrEnum):
    none = "none"
    payments = "payments"
    crm = "crm"
    erp = "erp"
    identity_sso = "identity_sso"
    email_notifications = "email_notifications"
    file_storage = "file_storage"
    analytics_bi = "analytics_bi"
    maps_geo = "maps_geo"
    messaging_chat = "messaging_chat"
    legacy_db = "legacy_db"
    third_party_api_unknown = "third_party_api_unknown"
    other = "other"


class HostingConstraint(StrEnum):
    no_preference = "no_preference"
    cloud_managed = "cloud_managed"
    customer_cloud_only = "customer_cloud_only"
    on_prem = "on_prem"
    air_gapped = "air_gapped"
    hybrid = "hybrid"


class TeamContext(StrEnum):
    client_only = "client_only"
    vendor_led = "vendor_led"
    mixed_team = "mixed_team"
    unknown = "unknown"


class UiLanguage(StrEnum):
    en = "en"
    es = "es"
    pt = "pt"
    fr = "fr"
    de = "de"
    other = "other"


class RiskLevel(StrEnum):
    low = "low"
    medium = "medium"
    high = "high"
    unknown = "unknown"


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
    deliverables: list[str] = Field(..., min_length=_DELIVERABLES_MIN, max_length=_DELIVERABLES_MAX)
    out_of_scope: list[str] | None = None
    delivery_urgency: DeliveryUrgency
    target_date: date | None = None
    delivery_approach: DeliveryApproach | None = None
    integration_categories: list[IntegrationCategory] = Field(default_factory=list)
    integration_custom_names: list[str] | None = None
    data_sensitivity: DataSensitivity
    hosting_constraints: list[HostingConstraint] | None = None
    hosting_notes: str | None = Field(default=None, max_length=_HOSTING_NOTES_MAX)
    team_context: TeamContext | None = None
    ui_languages: list[UiLanguage] = Field(default_factory=list, max_length=3)
    risk_level: RiskLevel | None = None
    external_dependencies: list[str] | None = None
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

    @field_validator("deliverables")
    @classmethod
    def deliverables_rules(cls, value: list[str]) -> list[str]:
        if len(value) < _DELIVERABLES_MIN or len(value) > _DELIVERABLES_MAX:
            raise ValueError(
                f"deliverables must contain between {_DELIVERABLES_MIN} and {_DELIVERABLES_MAX} items"
            )
        out: list[str] = []
        for item in value:
            s = item.strip()
            if not s:
                raise ValueError("deliverables items must not be empty after trim")
            if len(s) > _DELIVERABLE_ITEM_MAX:
                raise ValueError(f"each deliverable must be at most {_DELIVERABLE_ITEM_MAX} characters")
            out.append(s)
        return out

    @field_validator("out_of_scope")
    @classmethod
    def out_of_scope_rules(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        if len(value) > _OUT_OF_SCOPE_MAX_ITEMS:
            raise ValueError(f"out_of_scope may contain at most {_OUT_OF_SCOPE_MAX_ITEMS} items")
        out: list[str] = []
        for item in value:
            s = item.strip()
            if not s:
                raise ValueError("out_of_scope items must not be empty after trim")
            if len(s) > _DELIVERABLE_ITEM_MAX:
                raise ValueError(f"each out_of_scope line must be at most {_DELIVERABLE_ITEM_MAX} characters")
            out.append(s)
        return out

    @field_validator("integration_categories", mode="after")
    @classmethod
    def integration_none_exclusivity(cls, value: list[IntegrationCategory]) -> list[IntegrationCategory]:
        if IntegrationCategory.none in value:
            if len(value) > 1:
                raise ValueError("'none' cannot be combined with other integration_categories values")
            return []
        return value

    @field_validator("integration_custom_names")
    @classmethod
    def integration_custom_rules(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        if len(value) > _INTEGRATION_CUSTOM_MAX_ITEMS:
            raise ValueError(
                f"integration_custom_names may contain at most {_INTEGRATION_CUSTOM_MAX_ITEMS} entries"
            )
        out: list[str] = []
        for item in value:
            s = item.strip()
            if not s:
                raise ValueError("integration_custom_names items must not be empty after trim")
            if len(s) < _INTEGRATION_CUSTOM_MIN_LEN:
                raise ValueError(
                    f"each integration_custom_names entry must be at least {_INTEGRATION_CUSTOM_MIN_LEN} characters after trim"
                )
            if len(s) > _INTEGRATION_CUSTOM_MAX_LEN:
                raise ValueError(
                    f"each integration_custom_names entry must be at most {_INTEGRATION_CUSTOM_MAX_LEN} characters"
                )
            out.append(s)
        return out

    @field_validator("external_dependencies")
    @classmethod
    def external_dependencies_rules(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        if len(value) > _EXTERNAL_DEP_MAX_ITEMS:
            raise ValueError(f"external_dependencies may contain at most {_EXTERNAL_DEP_MAX_ITEMS} items")
        out: list[str] = []
        for item in value:
            s = item.strip()
            if not s:
                raise ValueError("external_dependencies items must not be empty after trim")
            if len(s) > _EXTERNAL_DEP_MAX_LEN:
                raise ValueError(
                    f"each external_dependencies line must be at most {_EXTERNAL_DEP_MAX_LEN} characters"
                )
            out.append(s)
        return out

    @field_validator("hosting_notes")
    @classmethod
    def hosting_notes_strip(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None

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
    def target_date_when_urgent(self) -> Self:
        if self.delivery_urgency in (DeliveryUrgency.fixed_date, DeliveryUrgency.critical):
            if self.target_date is None:
                raise ValueError("target_date is required when delivery_urgency is fixed_date or critical")
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
