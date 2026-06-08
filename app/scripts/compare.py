"""Cosine similarity CLI for embedding sanity checks (feature-034)."""

from __future__ import annotations

import argparse
import asyncio
import logging
import math
import sys

from app.config import get_settings
from app.embedding_pipeline.embedder import OpenAIEmbedder

logger = logging.getLogger(__name__)


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """Return cosine similarity between two vectors using stdlib math only."""
    if len(a) != len(b) or not a:
        return 0.0

    dot = math.fsum(x * y for x, y in zip(a, b, strict=True))
    norm_a = math.sqrt(math.fsum(x * x for x in a))
    norm_b = math.sqrt(math.fsum(y * y for y in b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


async def _embed_pair(
    embedder: OpenAIEmbedder,
    text_a: str,
    text_b: str,
) -> tuple[list[float], list[float]]:
    vector_a = await embedder.embed_one(text_a)
    vector_b = await embedder.embed_one(text_b)
    return vector_a, vector_b


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Compare cosine similarity between two text embeddings.",
    )
    parser.add_argument("--text-a", required=True, help="First text to embed")
    parser.add_argument("--text-b", required=True, help="Second text to embed")
    args = parser.parse_args(argv)

    try:
        embedder = OpenAIEmbedder(get_settings())
        vector_a, vector_b = asyncio.run(_embed_pair(embedder, args.text_a, args.text_b))
        similarity = cosine_similarity(vector_a, vector_b)
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        logger.exception(
            "compare_cli_failed",
            extra={"error_type": type(exc).__name__},
        )
        return 1

    print(f"Text A: {args.text_a}")
    print(f"Text B: {args.text_b}")
    print(f"Cosine similarity: {similarity:.4f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
