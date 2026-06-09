"""Preflight checks for the embedding pipeline."""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys

from app.config import get_settings
from app.embedding_pipeline.chunker import JSONStructuralChunker
from app.embedding_pipeline.embedder import OpenAIEmbedder

logger = logging.getLogger(__name__)


def _mask_key(key: str) -> str:
    stripped = key.strip()
    if len(stripped) <= 8:
        return "***"
    return f"{stripped[:3]}...{stripped[-4:]}"


async def _optional_live_ping(embedder: OpenAIEmbedder) -> None:
    vector = await embedder.embed_one("preflight ping")
    if not vector:
        raise RuntimeError("Live embedding returned an empty vector")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Embedding pipeline preflight checks.")
    parser.add_argument(
        "--skip-key-check",
        action="store_true",
        help="Do not require OPENAI_API_KEY",
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="Call OpenAI embeddings once (requires API key)",
    )
    args = parser.parse_args(argv)

    try:
        settings = get_settings()
        key = settings.openai_api_key.strip()
        if not key and not args.skip_key_check:
            print("Error: OPENAI_API_KEY is not configured.", file=sys.stderr)
            return 1

        model = settings.embedding_pipeline_model.strip() or "text-embedding-3-small"
        JSONStructuralChunker(embedding_model=model)
        print(f"settings=ok model={model}")

        if key:
            print(f"openai_api_key={_mask_key(key)}")
        elif args.skip_key_check:
            print("openai_api_key=skipped")

        if args.live:
            embedder = OpenAIEmbedder(settings)
            asyncio.run(_optional_live_ping(embedder))
            print("live_embedding=ok")

        return 0
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        logger.exception(
            "preflight_embedding_pipeline_failed",
            extra={"error_type": type(exc).__name__},
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
