"""Parser tests for technical doc ingest (feature-063)."""

from __future__ import annotations

from app.embedding_pipeline.parsers.technical_doc import parse_technical_doc_text


def test_parse_technical_doc_sections() -> None:
    text = "# Architecture\n\nSystem overview.\n\n## API\n\nREST endpoints."
    segments = parse_technical_doc_text(
        text,
        source_path="docs/arch.md",
        doc_id="arch-1",
        version="1.0",
    )
    assert len(segments) == 2
    assert segments[0].metadata["section_title"] == "Architecture"
