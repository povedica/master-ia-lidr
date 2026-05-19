"""Derive UI-facing project metadata from simplified session input."""

from __future__ import annotations

from app.schemas.simplified_session import SessionEstimateRequest
from app.services.document_extractor import ExtractedAttachment
from app.services.sessions import DerivedProjectMetadata


def derive_project_metadata(
    request: SessionEstimateRequest,
    *,
    extracted: list[ExtractedAttachment],
    warnings: list[str],
) -> DerivedProjectMetadata:
    """Combine explicit fields, transcript, and attachment signals into metadata."""

    summary = request.one_line_summary or request.transcript.strip()[:500]
    deliverables = _bullet_lines(request.transcript)
    constraints = _constraint_lines(request.transcript)
    attachment_summary = _attachment_summary(extracted)
    confidence = list(warnings)
    if not deliverables:
        confidence.append("deliverables were inferred from transcript structure, not explicit lists")

    return DerivedProjectMetadata(
        project_name=request.project_name,
        project_type=request.project_type,
        target_audience=request.target_audience,
        industry=request.industry,
        summary=summary,
        derived_deliverables=deliverables,
        detected_constraints=constraints,
        attachment_summary=attachment_summary,
        confidence_notes=confidence,
    )


def _bullet_lines(text: str) -> list[str]:
    items: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith(("-", "*", "•")):
            item = stripped.lstrip("-*• ").strip()
            if item:
                items.append(item[:120])
    return items[:8]


def _constraint_lines(text: str) -> list[str]:
    keywords = ("must", "cannot", "constraint", "deadline", "compliance", "gdpr", "sla")
    found: list[str] = []
    for line in text.splitlines():
        lower = line.lower()
        if any(word in lower for word in keywords):
            stripped = line.strip()
            if stripped:
                found.append(stripped[:160])
    return found[:5]


def _attachment_summary(extracted: list[ExtractedAttachment]) -> str | None:
    if not extracted:
        return None
    names = [item.filename for item in extracted if item.text.strip()]
    if not names:
        return "Attachments provided but no extractable text was found."
    return f"Processed attachments: {', '.join(names)}"
