"""Parser tests for transcript ingest (feature-063)."""

from __future__ import annotations

from pathlib import Path

from app.embedding_pipeline.parsers.transcript_txt import parse_transcript_text

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "sample_transcript.txt"


def test_parse_transcript_tagged_turns() -> None:
    text = FIXTURE.read_text(encoding="utf-8")
    segments = parse_transcript_text(
        text,
        source_path=str(FIXTURE),
        transcript_id="demo-transcript",
    )
    assert len(segments) >= 3
    assert segments[0].metadata["format_mode"] == "tagged"
    assert "Alice" in segments[0].content
