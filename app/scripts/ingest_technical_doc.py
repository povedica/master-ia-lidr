#!/usr/bin/env python3
"""CLI ingest for technical documentation files (feature-063)."""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

from app.config import get_settings
from app.database import get_session_factory
from app.embedding_pipeline.collections import Collection
from app.embedding_pipeline.embedder import OpenAIEmbedder
from app.embedding_pipeline.parsers.technical_doc import (
    CHUNK_TYPE_DOC_SECTION,
    parse_technical_doc_text,
)
from app.embedding_pipeline.text_corpus_ingest import run_text_corpus_ingest


async def _main() -> None:
    parser = argparse.ArgumentParser(description="Ingest a technical doc file into Postgres.")
    parser.add_argument("path", type=Path, help="Path to markdown or text file")
    parser.add_argument("--doc-id", required=True, help="Stable document identifier")
    parser.add_argument("--version", default=None, help="Optional document version label")
    args = parser.parse_args()

    settings = get_settings()
    raw_text = args.path.read_text(encoding="utf-8")
    segments = parse_technical_doc_text(
        raw_text,
        source_path=str(args.path),
        doc_id=args.doc_id,
        version=args.version,
    )
    embedder = OpenAIEmbedder(settings)
    factory = get_session_factory(settings)
    async with factory() as session:
        result = await run_text_corpus_ingest(
            session,
            source_path=str(args.path),
            document_type="technical_doc",
            collection=Collection.TECHNICAL_DOCS.value,
            chunk_type=CHUNK_TYPE_DOC_SECTION,
            segments=segments,
            embedder=embedder,
            document_metadata={"doc_id": args.doc_id, "version": args.version},
        )
    print(
        f"Ingested technical doc {args.doc_id}: "
        f"document_id={result.document_id} chunks={result.chunks_created}"
    )


if __name__ == "__main__":
    asyncio.run(_main())
