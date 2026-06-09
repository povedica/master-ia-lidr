"""Offline CAG vs RAG vs Hybrid recommendation heuristics."""

from __future__ import annotations

import argparse
import sys


def recommend(corpus_tokens: int, refresh_days: int) -> str:
    """Return CAG, Hybrid, or RAG based on simple token and refresh heuristics."""
    if corpus_tokens <= 8_000 and refresh_days >= 30:
        return "CAG"
    if corpus_tokens >= 80_000 or refresh_days <= 7:
        return "RAG"
    return "Hybrid"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Recommend CAG, Hybrid, or RAG for a corpus profile.",
    )
    parser.add_argument(
        "--corpus-tokens",
        type=int,
        required=True,
        help="Estimated total tokens in the knowledge corpus",
    )
    parser.add_argument(
        "--refresh-days",
        type=int,
        required=True,
        help="Typical days between corpus refreshes",
    )
    args = parser.parse_args(argv)

    if args.corpus_tokens < 0 or args.refresh_days < 0:
        print("Error: corpus-tokens and refresh-days must be non-negative.", file=sys.stderr)
        return 1

    decision = recommend(args.corpus_tokens, args.refresh_days)
    print(decision)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
