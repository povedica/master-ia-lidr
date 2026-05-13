"""Deterministic post-generation checks when ``evaluate=true`` (mode-specific; separate from API ``score``)."""

from __future__ import annotations

from app.schemas.estimations import OutputValidationView
from app.services.estimation_engine import (
    EstimationMode,
    required_section_presence,
    validate_mode_output,
)

_OK_FINISH_REASONS = frozenset({"stop", "end_turn"})


def evaluate_estimation_output(
    markdown: str,
    mode: EstimationMode,
    finish_reason: str | None,
) -> OutputValidationView:
    """Score output shape using mode-required sections and a safe finish_reason allowlist."""

    sections = required_section_presence(markdown, mode)
    structure_valid = validate_mode_output(markdown, mode)
    fr = finish_reason or "stop"
    finish_ok = fr in _OK_FINISH_REASONS

    issues: list[str] = []
    for name, ok in sections.items():
        if not ok:
            issues.append(f"Missing required section keyword: {name!r}")
    if not structure_valid:
        issues.append("Mode structure validation failed (aggregate required sections).")
    if not finish_ok:
        issues.append(f"Unexpected finish_reason={finish_reason!r} (expected one of {_OK_FINISH_REASONS})")

    return OutputValidationView(
        mode=mode,
        finish_reason=finish_reason,
        finish_reason_ok=finish_ok,
        structure_valid=structure_valid,
        required_sections=sections,
        issues=issues,
    )
