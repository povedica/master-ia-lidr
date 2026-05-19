"""Unit tests for cross-turn derived metadata merge."""

from __future__ import annotations

from app.schemas.estimation_request import Industry, ProjectType, TargetAudience
from app.services.sessions import DerivedProjectMetadata
from app.services.simplified_session_metadata_merge import merge_derived_metadata


def _meta(
    *,
    project_name: str = "Acme Portal",
    summary: str | None = "Turn summary",
    constraints: list[str] | None = None,
    attachment_summary: str | None = None,
    confidence_notes: list[str] | None = None,
    industry: Industry | None = Industry.fintech,
) -> DerivedProjectMetadata:
    return DerivedProjectMetadata(
        project_name=project_name,
        project_type=ProjectType.web_saas,
        target_audience=TargetAudience.b2b_smb,
        industry=industry,
        summary=summary,
        detected_constraints=constraints or [],
        attachment_summary=attachment_summary,
        confidence_notes=confidence_notes or [],
    )


def test_merge_with_no_previous_returns_incoming() -> None:
    incoming = _meta()
    merged = merge_derived_metadata(None, incoming)
    assert merged == incoming


def test_merge_keeps_previous_project_name_when_incoming_empty() -> None:
    previous = _meta(project_name="Acme Portal")
    incoming = _meta(project_name="", summary="New turn")
    merged = merge_derived_metadata(previous, incoming)
    assert merged.project_name == "Acme Portal"
    assert merged.summary == "New turn"


def test_merge_unions_constraints_deduped_and_capped() -> None:
    previous = _meta(constraints=["Must use PostgreSQL", "  GDPR compliance  "])
    incoming = _meta(
        constraints=["gdpr compliance", "Redis caching required", "Extra A", "Extra B", "Extra C"]
    )
    merged = merge_derived_metadata(previous, incoming)
    assert len(merged.detected_constraints) <= 5
    normalized = {line.strip().lower() for line in merged.detected_constraints}
    assert "must use postgresql" in normalized
    assert "gdpr compliance" in normalized


def test_merge_replaces_attachment_summary_when_incoming_non_empty() -> None:
    previous = _meta(attachment_summary="Old files")
    incoming = _meta(attachment_summary="Processed attachments: spec.pdf")
    merged = merge_derived_metadata(previous, incoming)
    assert merged.attachment_summary == "Processed attachments: spec.pdf"


def test_merge_keeps_previous_attachment_summary_when_incoming_empty() -> None:
    previous = _meta(attachment_summary="Old files")
    incoming = _meta(attachment_summary=None)
    merged = merge_derived_metadata(previous, incoming)
    assert merged.attachment_summary == "Old files"


def test_merge_appends_confidence_notes_deduped() -> None:
    previous = _meta(confidence_notes=["warn-a"])
    incoming = _meta(confidence_notes=["warn-b", "warn-a"])
    merged = merge_derived_metadata(previous, incoming)
    assert merged.confidence_notes == ["warn-a", "warn-b"]
