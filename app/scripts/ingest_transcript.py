#!/usr/bin/env python3
"""CLI ingest for meeting transcript text files (feature-063 / feature-065)."""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

from app.config import get_settings
from app.database import get_session_factory
from app.embedding_pipeline.collections import Collection
from app.embedding_pipeline.embedder import OpenAIEmbedder
from app.embedding_pipeline.parsers.transcript_txt import (
    CHUNK_TYPE_MEETING_SEGMENT,
    parse_transcript_text,
)
from app.embedding_pipeline.pii.redactor import RegexPiiAnalyzer, redact_transcript
from app.embedding_pipeline.text_corpus_ingest import run_text_corpus_ingest


async def _main() -> None:
    parser = argparse.ArgumentParser(description="Ingest a transcript text file into Postgres.")
    parser.add_argument("path", type=Path, help="Path to transcript .txt file")
    parser.add_argument("--transcript-id", required=True, help="Stable transcript identifier")
    args = parser.parse_args()

    settings = get_settings()
    raw_text = args.path.read_text(encoding="utf-8")
    analyzer = RegexPiiAnalyzer() if settings.transcript_pii_enabled else None
    redacted = redact_transcript(raw_text, enabled=settings.transcript_pii_enabled, analyzer=analyzer)
    segments = parse_transcript_text(
        redacted.text,
        source_path=str(args.path),
        transcript_id=args.transcript_id,
    )
    embedder = OpenAIEmbedder(settings)
    factory = get_session_factory(settings)
    async with factory() as session:
        result = await run_text_corpus_ingest(
            session,
            source_path=str(args.path),
            document_type="transcript",
            collection=Collection.TRANSCRIPTS.value,
            chunk_type=CHUNK_TYPE_MEETING_SEGMENT,
            segments=segments,
            embedder=embedder,
            document_metadata={"transcript_id": args.transcript_id},
        )
    print(
        f"Ingested transcript {args.transcript_id}: "
        f"document_id={result.document_id} chunks={result.chunks_created} "
        f"pii_redacted={redacted.entities_redacted}"
    )


if __name__ == "__main__":
    asyncio.run(_main())
