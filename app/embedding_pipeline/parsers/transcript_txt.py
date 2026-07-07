"""Parse meeting transcript text into retrievable segments (feature-063)."""

from __future__ import annotations

import re
from dataclasses import dataclass

_TURN_RE = re.compile(
    r"^\[(?P<timestamp>\d{2}:\d{2}:\d{2})\]\s+(?P<speaker>[^:]+):\s+(?P<text>.+)$"
)
CHUNK_TYPE_MEETING_SEGMENT = "meeting_segment"


@dataclass(frozen=True)
class TranscriptSegment:
    segment_id: str
    content: str
    metadata: dict[str, object]


def _has_speaker_tags(text: str) -> bool:
    matches = sum(1 for line in text.splitlines() if _TURN_RE.match(line.strip()))
    return matches >= 3


def parse_transcript_text(
    text: str,
    *,
    source_path: str,
    transcript_id: str,
) -> list[TranscriptSegment]:
    """Return one segment per tagged turn or per legacy paragraph block."""

    if _has_speaker_tags(text):
        return _parse_tagged(text, source_path=source_path, transcript_id=transcript_id)
    return _parse_legacy(text, source_path=source_path, transcript_id=transcript_id)


def _parse_tagged(text: str, *, source_path: str, transcript_id: str) -> list[TranscriptSegment]:
    segments: list[TranscriptSegment] = []
    for index, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue
        match = _TURN_RE.match(line)
        if match is None:
            continue
        speaker = match.group("speaker").strip()
        body = match.group("text").strip()
        if not body:
            continue
        segments.append(
            TranscriptSegment(
                segment_id=f"{transcript_id}:turn-{index:04d}",
                content=f"{speaker}: {body}",
                metadata={
                    "transcript_id": transcript_id,
                    "speaker": speaker,
                    "timestamp": match.group("timestamp"),
                    "format_mode": "tagged",
                    "source_path": source_path,
                },
            )
        )
    return segments


def _parse_legacy(text: str, *, source_path: str, transcript_id: str) -> list[TranscriptSegment]:
    segments: list[TranscriptSegment] = []
    blocks = [block.strip() for block in re.split(r"\n\s*\n", text) if block.strip()]
    for index, block in enumerate(blocks, start=1):
        segments.append(
            TranscriptSegment(
                segment_id=f"{transcript_id}:block-{index:04d}",
                content=block,
                metadata={
                    "transcript_id": transcript_id,
                    "format_mode": "legacy",
                    "block_index": index,
                    "source_path": source_path,
                },
            )
        )
    return segments
