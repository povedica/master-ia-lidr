#!/usr/bin/env python3
"""Run retrieval mode evaluation over the golden set (feature-050)."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

from app.config import Settings
from app.database import get_session_factory, reset_session_factory
from app.embedding_pipeline.embedder import OpenAIEmbedder
from app.embedding_pipeline.rerank import build_reranker
from app.embedding_pipeline.retrieval_eval import (
    QueryModeResult,
    detect_noop_rerank_warning,
    load_golden_set,
    metrics_to_json,
    precision_at_5,
    render_comparison_markdown,
    render_recommendation_markdown,
    summarize_mode_metrics,
)
from app.embedding_pipeline.retrieval_service import RetrievalMode, RetrievalService


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate retrieval modes A/B/C/D.")
    parser.add_argument(
        "--golden-set",
        type=Path,
        default=Path("evaluation/retrieval/golden_set.json"),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Defaults to evaluation/retrieval/results/<timestamp>/",
    )
    parser.add_argument("--repetitions", type=int, default=5)
    parser.add_argument("--warmup", action="store_true", default=True)
    return parser.parse_args()


async def _run_evaluation(args: argparse.Namespace) -> int:
    settings = Settings()
    if not settings.database_url.strip():
        print("DATABASE_URL is required for retrieval evaluation.", file=sys.stderr)
        return 1

    golden_queries = load_golden_set(args.golden_set)
    service = RetrievalService()
    embedder = OpenAIEmbedder(settings)
    reranker = build_reranker(settings)
    noop_warnings = [
        warning
        for mode in (RetrievalMode.C, RetrievalMode.D)
        if (warning := detect_noop_rerank_warning(mode=mode, rerank_is_noop=reranker.is_noop))
    ]
    if noop_warnings:
        for warning in noop_warnings:
            print(warning, file=sys.stderr)
        return 2

    reset_session_factory()
    session_factory = get_session_factory(settings)
    all_mode_results: dict[RetrievalMode, list[QueryModeResult]] = {
        mode: [] for mode in RetrievalMode
    }

    async with session_factory() as session:
        for golden in golden_queries:
            for mode in RetrievalMode:
                samples: list[float] = []
                retrieved_budget_ids: list[str] = []
                if args.warmup:
                    await service.retrieve(
                        golden.query,
                        mode=mode,
                        recall_k=settings.retrieval_recall_k,
                        top_k_final=settings.retrieval_top_k_final,
                        session=session,
                        embedder=embedder,
                        reranker=reranker,
                        settings=settings,
                    )
                for _ in range(args.repetitions):
                    started = time.perf_counter()
                    response = await service.retrieve(
                        golden.query,
                        mode=mode,
                        recall_k=settings.retrieval_recall_k,
                        top_k_final=settings.retrieval_top_k_final,
                        session=session,
                        embedder=embedder,
                        reranker=reranker,
                        settings=settings,
                    )
                    samples.append((time.perf_counter() - started) * 1000)
                    retrieved_budget_ids = [
                        row.budget_id or "" for row in response.results if row.budget_id
                    ]
                hits = tuple(
                    budget_id
                    for budget_id in retrieved_budget_ids
                    if budget_id in golden.relevant_budget_ids
                )
                all_mode_results[mode].append(
                    QueryModeResult(
                        query_id=golden.id,
                        mode=mode,
                        precision_at_5=precision_at_5(
                            retrieved_budget_ids,
                            golden.relevant_budget_ids,
                        ),
                        latency_ms_samples=tuple(samples),
                        retrieved_budget_ids=tuple(retrieved_budget_ids),
                        hit_budget_ids=hits,
                    )
                )

    metrics = [summarize_mode_metrics(results) for results in all_mode_results.values()]
    timestamp = datetime.now(tz=UTC).strftime("%Y%m%dT%H%M%SZ")
    output_dir = args.output_dir or Path("evaluation/retrieval/results") / timestamp
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "results.json").write_text(
        json.dumps(metrics_to_json(metrics), indent=2),
        encoding="utf-8",
    )
    (output_dir / "comparison.md").write_text(
        render_comparison_markdown(metrics),
        encoding="utf-8",
    )
    (output_dir / "recommendation.md").write_text(
        render_recommendation_markdown(metrics),
        encoding="utf-8",
    )
    print(f"Wrote evaluation artifacts to {output_dir}")
    return 0


def main() -> int:
    args = _parse_args()
    return asyncio.run(_run_evaluation(args))


if __name__ == "__main__":
    raise SystemExit(main())
