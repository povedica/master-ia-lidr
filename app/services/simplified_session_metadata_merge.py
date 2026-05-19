"""Merge derived project metadata across simplified session submits."""

from __future__ import annotations

from app.services.sessions import DerivedProjectMetadata

_CONSTRAINT_CAP = 5


def merge_derived_metadata(
    previous: DerivedProjectMetadata | None,
    incoming: DerivedProjectMetadata,
) -> DerivedProjectMetadata:
    """Combine prior session memory with metadata from the current submit."""

    if previous is None:
        return incoming

    return DerivedProjectMetadata(
        project_name=_merge_scalar(previous.project_name, incoming.project_name),
        project_type=incoming.project_type or previous.project_type,
        target_audience=incoming.target_audience or previous.target_audience,
        industry=incoming.industry if incoming.industry is not None else previous.industry,
        summary=incoming.summary or previous.summary,
        detected_constraints=_merge_constraints(
            previous.detected_constraints,
            incoming.detected_constraints,
        ),
        attachment_summary=_merge_attachment_summary(
            previous.attachment_summary,
            incoming.attachment_summary,
        ),
        confidence_notes=_merge_confidence_notes(
            previous.confidence_notes,
            incoming.confidence_notes,
        ),
    )


def _merge_scalar(previous: str, incoming: str) -> str:
    stripped = incoming.strip()
    return stripped if stripped else previous


def _normalize_constraint(line: str) -> str:
    return line.strip().lower()


def _merge_constraints(previous: list[str], incoming: list[str]) -> list[str]:
    seen: set[str] = set()
    merged: list[str] = []
    for line in (*previous, *incoming):
        key = _normalize_constraint(line)
        if not key or key in seen:
            continue
        seen.add(key)
        merged.append(line.strip())
        if len(merged) >= _CONSTRAINT_CAP:
            break
    return merged


def _merge_attachment_summary(previous: str | None, incoming: str | None) -> str | None:
    if incoming and incoming.strip():
        return incoming
    return previous


def _merge_confidence_notes(previous: list[str], incoming: list[str]) -> list[str]:
    seen: set[str] = set()
    merged: list[str] = []
    for note in (*previous, *incoming):
        if not note or note in seen:
            continue
        seen.add(note)
        merged.append(note)
    return merged
