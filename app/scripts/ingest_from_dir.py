"""Ingest budget JSON files from a directory through the embedding pipeline."""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path

from app.config import get_settings
from app.embedding_pipeline.chunker import JSONStructuralChunker
from app.embedding_pipeline.embedder import OpenAIEmbedder
from app.embedding_pipeline.ingest import run_ingest
from app.embedding_pipeline.loaders.filesystem import FileSystemLoader
from app.embedding_pipeline.parsers.registry import get_parser

logger = logging.getLogger(__name__)


def _build_chunker(settings) -> JSONStructuralChunker:
    model = settings.embedding_pipeline_model.strip() or "text-embedding-3-small"
    return JSONStructuralChunker(embedding_model=model)


async def _run(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Load budget JSON files, chunk, and optionally embed.",
    )
    parser.add_argument(
        "--dir",
        required=True,
        type=Path,
        help="Directory with budget *.json files (non-recursive)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Chunk only; do not call OpenAI embeddings",
    )
    args = parser.parse_args(argv)

    try:
        settings = get_settings()
        parse_budget = get_parser("json")
        budgets = [parse_budget(path) for path in FileSystemLoader.iter_budget_files(args.dir)]
        chunker = _build_chunker(settings)

        if args.dry_run:
            chunks = chunker.chunk(budgets)
            first_id = chunks[0].chunk_id if chunks else ""
            print(f"chunks={len(chunks)} first_chunk_id={first_id}")
            return 0

        embedder = OpenAIEmbedder(settings)
        response = await run_ingest(budgets, chunker, embedder)
        stats = response.stats
        print(
            "total_budgets={total_budgets} total_chunks={total_chunks} "
            "total_tokens={total_tokens} estimated_cost_usd={estimated_cost_usd:.8f}".format(
                total_budgets=stats.total_budgets,
                total_chunks=stats.total_chunks,
                total_tokens=stats.total_tokens,
                estimated_cost_usd=stats.estimated_cost_usd,
            )
        )
        return 0
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        logger.exception(
            "ingest_from_dir_failed",
            extra={"error_type": type(exc).__name__},
        )
        return 1


def main(argv: list[str] | None = None) -> int:
    return asyncio.run(_run(argv))


if __name__ == "__main__":
    raise SystemExit(main())
