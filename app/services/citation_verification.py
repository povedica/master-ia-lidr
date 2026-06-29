"""Post-generation citation membership verification (pure domain)."""

from __future__ import annotations

from collections import Counter

from app.schemas.citation_report import (
    CitationLineReport,
    CitationLineStatus,
    CitationReport,
)
from app.schemas.rag_estimation_result import RagEstimationLineItem, RagEstimationResult


def verify_citations(
    estimate: RagEstimationResult,
    retrieved_chunk_ids: set[int],
    *,
    request_id: str,
) -> CitationReport:
    """Classify each line by citation membership against the retrieved context."""

    lines: list[CitationLineReport] = []
    for index, item in enumerate(estimate.line_items):
        status, invalid_ids = _classify_line(item, retrieved_chunk_ids)
        lines.append(
            CitationLineReport(
                index=index,
                component=item.component,
                status=status,
                invalid_chunk_ids=invalid_ids,
            )
        )

    counts = Counter(line.status for line in lines)
    count_map = {status: counts.get(status, 0) for status in CitationLineStatus}
    return CitationReport(
        request_id=request_id,
        lines=lines,
        counts=count_map,
        has_dangling=counts.get(CitationLineStatus.DANGLING_CITATION, 0) > 0,
        has_integrity_violation=counts.get(CitationLineStatus.INTEGRITY_VIOLATION, 0) > 0,
    )


def _classify_line(
    item: RagEstimationLineItem,
    retrieved_chunk_ids: set[int],
) -> tuple[CitationLineStatus, list[int]]:
    if item.grounded:
        if not item.sources:
            return CitationLineStatus.INTEGRITY_VIOLATION, []
        invalid = [source.chunk_id for source in item.sources if source.chunk_id not in retrieved_chunk_ids]
        if invalid:
            return CitationLineStatus.DANGLING_CITATION, invalid
        return CitationLineStatus.GROUNDED_OK, []

    if not item.sources and item.hours == 0:
        return CitationLineStatus.INSUFFICIENT_DATA, []

    return CitationLineStatus.INTEGRITY_VIOLATION, []
