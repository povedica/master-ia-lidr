"""Parse technical documentation into section chunks (feature-063)."""

from __future__ import annotations

import re
from dataclasses import dataclass

_SECTION_RE = re.compile(r"^(#{1,3})\s+(.+)$", re.MULTILINE)
CHUNK_TYPE_DOC_SECTION = "doc_section"


@dataclass(frozen=True)
class TechnicalDocSegment:
    segment_id: str
    content: str
    metadata: dict[str, object]


def parse_technical_doc_text(
    text: str,
    *,
    source_path: str,
    doc_id: str,
    version: str | None = None,
) -> list[TechnicalDocSegment]:
    """Split markdown-ish docs on headings; fallback to paragraph blocks."""

    matches = list(_SECTION_RE.finditer(text))
    if not matches:
        return _paragraph_segments(text, source_path=source_path, doc_id=doc_id, version=version)

    segments: list[TechnicalDocSegment] = []
    for index, match in enumerate(matches):
        start = match.start()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        section_title = match.group(2).strip()
        body = text[start:end].strip()
        if not body:
            continue
        segments.append(
            TechnicalDocSegment(
                segment_id=f"{doc_id}:section-{index + 1:04d}",
                content=body,
                metadata={
                    "doc_id": doc_id,
                    "section_title": section_title,
                    "version": version,
                    "source_path": source_path,
                },
            )
        )
    return segments


def _paragraph_segments(
    text: str,
    *,
    source_path: str,
    doc_id: str,
    version: str | None,
) -> list[TechnicalDocSegment]:
    segments: list[TechnicalDocSegment] = []
    blocks = [block.strip() for block in re.split(r"\n\s*\n", text) if block.strip()]
    for index, block in enumerate(blocks, start=1):
        segments.append(
            TechnicalDocSegment(
                segment_id=f"{doc_id}:block-{index:04d}",
                content=block,
                metadata={
                    "doc_id": doc_id,
                    "version": version,
                    "block_index": index,
                    "source_path": source_path,
                },
            )
        )
    return segments
