"""Post-generation structural coherence verification (pure domain).

Rules (deterministic, no LLM):
1. ``total_hours`` must match the sum of ``line_items[].hours`` within tolerance.
2. ``component`` names must be unique (case-insensitive).
3. When ``insufficient_context`` is true, ``line_items`` must be empty.
4. Grounded lines with ``hours == 0`` but non-empty rationale are flagged.
"""

from __future__ import annotations

import logging
from collections import Counter

from app.schemas.coherence_report import (
    CoherenceLineReport,
    CoherenceLineStatus,
    CoherenceReport,
)
from app.schemas.rag_estimation_result import RagEstimationLineItem, RagEstimationResult

logger = logging.getLogger(__name__)

_DEFAULT_TOTAL_TOLERANCE = 0.01


def check_coherence(
    estimate: RagEstimationResult,
    *,
    request_id: str,
    enabled: bool = True,
    total_tolerance: float = _DEFAULT_TOTAL_TOLERANCE,
) -> CoherenceReport:
    """Classify estimate and line items for internal structural coherence."""

    if not enabled:
        return _noop_report(request_id)

    lines: list[CoherenceLineReport] = []
    duplicate_indices = _duplicate_component_indices(estimate.line_items)

    if estimate.insufficient_context and estimate.line_items:
        lines.append(
            CoherenceLineReport(
                index=-1,
                component="__estimate__",
                status=CoherenceLineStatus.INSUFFICIENT_CONTEXT_VIOLATION,
            )
        )

    line_sum = sum(item.hours for item in estimate.line_items)
    if estimate.line_items and abs(estimate.total_hours - line_sum) > total_tolerance:
        lines.append(
            CoherenceLineReport(
                index=-1,
                component="__total__",
                status=CoherenceLineStatus.TOTAL_HOURS_MISMATCH,
            )
        )

    for index, item in enumerate(estimate.line_items):
        status = _classify_line(item, index in duplicate_indices)
        lines.append(
            CoherenceLineReport(
                index=index,
                component=item.component,
                status=status,
            )
        )

    counts = Counter(line.status for line in lines)
    count_map = {status: counts.get(status, 0) for status in CoherenceLineStatus}
    has_violations = any(
        line.status != CoherenceLineStatus.COHERENT_OK for line in lines
    )
    report = CoherenceReport(
        request_id=request_id,
        lines=lines,
        counts=count_map,
        has_violations=has_violations,
    )
    _log_report(report)
    return report


def _classify_line(item: RagEstimationLineItem, is_duplicate: bool) -> CoherenceLineStatus:
    if is_duplicate:
        return CoherenceLineStatus.DUPLICATE_COMPONENT
    if item.grounded and item.hours == 0 and item.rationale.strip():
        return CoherenceLineStatus.ZERO_HOURS_GROUNDED
    return CoherenceLineStatus.COHERENT_OK


def _duplicate_component_indices(items: list[RagEstimationLineItem]) -> set[int]:
    seen: dict[str, int] = {}
    duplicates: set[int] = set()
    for index, item in enumerate(items):
        key = item.component.casefold()
        if key in seen:
            duplicates.add(index)
        else:
            seen[key] = index
    return duplicates


def _noop_report(request_id: str) -> CoherenceReport:
    return CoherenceReport(
        request_id=request_id,
        lines=[],
        counts={status: 0 for status in CoherenceLineStatus},
        has_violations=False,
    )


def _log_report(report: CoherenceReport) -> None:
    logger.info(
        "coherence_check_completed",
        extra={
            "request_id": report.request_id,
            "coherent_ok": report.counts.get(CoherenceLineStatus.COHERENT_OK, 0),
            "total_hours_mismatch": report.counts.get(
                CoherenceLineStatus.TOTAL_HOURS_MISMATCH, 0
            ),
            "duplicate_component": report.counts.get(
                CoherenceLineStatus.DUPLICATE_COMPONENT, 0
            ),
            "insufficient_context_violation": report.counts.get(
                CoherenceLineStatus.INSUFFICIENT_CONTEXT_VIOLATION, 0
            ),
            "zero_hours_grounded": report.counts.get(
                CoherenceLineStatus.ZERO_HOURS_GROUNDED, 0
            ),
            "has_violations": report.has_violations,
        },
    )
    for line in report.lines:
        if line.status == CoherenceLineStatus.COHERENT_OK:
            continue
        logger.warning(
            "coherence_violation",
            extra={
                "request_id": report.request_id,
                "component": line.component,
                "status": line.status.value,
                "index": line.index,
            },
        )
