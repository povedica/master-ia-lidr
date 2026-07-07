"""Post-generation hallucination gate (numeric anchors + per-line grades).

Pure helpers in step 1; judge and service wiring land in later steps.
"""

from __future__ import annotations

import re
from collections.abc import Sequence

from app.schemas.hallucination_report import HallucinationLineGrade

_DEFAULT_TOLERANCE = 0.25

_HOUR_PATTERN = re.compile(
    r"(?i)\b(\d+(?:\.\d+)?)\s*(?:hours?|hrs?|h)\b"
)


def numeric_anchor(chunk_texts: Sequence[str]) -> list[float]:
    """Extract hour-like numeric values from chunk texts deterministically."""

    values: list[float] = []
    for text in chunk_texts:
        for match in _HOUR_PATTERN.finditer(text):
            values.append(float(match.group(1)))
    return sorted(values)


def gate_line(
    *,
    line_hours: float,
    anchor_hours: Sequence[float],
    tolerance: float = _DEFAULT_TOLERANCE,
) -> HallucinationLineGrade:
    """Grade one line by comparing claimed hours to numeric anchors."""

    if not anchor_hours:
        return HallucinationLineGrade.INSUFFICIENT

    anchor_max = max(anchor_hours)
    if anchor_max <= 0:
        return HallucinationLineGrade.INSUFFICIENT

    upper_bound = anchor_max * (1.0 + tolerance)
    if line_hours <= upper_bound:
        return HallucinationLineGrade.GROUNDED
    return HallucinationLineGrade.DEGRADED
