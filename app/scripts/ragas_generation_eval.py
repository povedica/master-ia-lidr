#!/usr/bin/env python3
"""Run RAGAS generation evaluation over the generation golden set (feature-052)."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

from app.config import Settings
from app.database import get_session_factory, reset_session_factory
from app.embedding_pipeline.chunk_content_repository import ChunkContentRepository
from app.embedding_pipeline.embedder import OpenAIEmbedder
from app.embedding_pipeline.generation_eval import (
    RagasSample,
    build_ragas_records,
    extract_per_query_metrics,
    load_generation_golden_set,
    metrics_to_json,
    render_generation_comparison_markdown,
    render_quality_note,
    run_ragas_evaluation,
    summarize_generation_metrics,
    validate_generation_preflight,
)
from app.embedding_pipeline.retrieval_eval import fetch_alembic_revision, fetch_corpus_snapshot
from app.embedding_pipeline.retrieval_service import RetrievalMode, parse_retrieval_mode
from app.embedding_pipeline.rerank import build_reranker
from app.services.llm_chain import build_provider_chain
from app.services.rag_estimation_service import RagEstimationService
from app.embedding_pipeline.retrieval_service import RetrievalService


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate grounded generation with RAGAS.")
    parser.add_argument(
        "--golden-set",
        type=Path,
        default=Path("evaluation/generation/golden_set.json"),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Defaults to evaluation/generation/results/<timestamp>/",
    )
    return parser.parse_args()


async def _run_evaluation(args: argparse.Namespace) -> int:
    settings = Settings()
    golden_queries = load_generation_golden_set(args.golden_set)
    retrieval_service = RetrievalService()
    rag_service = RagEstimationService(
        settings=settings,
        retrieval_service=retrieval_service,
        content_repository=ChunkContentRepository(),
        providers=build_provider_chain(settings),
    )
    embedder = OpenAIEmbedder(settings)
    reranker = build_reranker(settings)
    mode = parse_retrieval_mode(settings.rag_estimation_retrieval_mode)

    reset_session_factory()
    session_factory = get_session_factory(settings)
    async with session_factory() as session:
        alembic_revision = await fetch_alembic_revision(session)
        corpus = await fetch_corpus_snapshot(session)
        ok, errors = validate_generation_preflight(
            settings=settings,
            corpus=corpus,
            alembic_revision=alembic_revision,
        )
        if not ok:
            for error in errors:
                print(error, file=sys.stderr)
            return 2

    samples: list[RagasSample] = []
    reset_session_factory()
    session_factory = get_session_factory(settings)
    async with session_factory() as session:
        for golden in golden_queries:
            outcome = await rag_service.estimate(
                golden.question,
                request_id=f"ragas_{golden.id}",
                session=session,
                embedder=embedder,
                reranker=reranker,
                mode=mode,
                recall_k=settings.retrieval_recall_k,
                top_k_final=settings.retrieval_top_k_final,
            )
            samples.append(
                RagasSample(
                    query_id=golden.id,
                    question=golden.question,
                    answer=outcome.result.model_dump_json(),
                    contexts=list(outcome.chunk_texts),
                    ground_truth=golden.ground_truth,
                )
            )

    records = build_ragas_records(samples)
    evaluate_result = run_ragas_evaluation(
        records,
        judge_model=settings.ragas_judge_model,
        embedding_model=settings.ragas_embedding_model,
        api_key=settings.openai_api_key,
    )
    per_query = extract_per_query_metrics(
        evaluate_result,
        query_ids=[sample.query_id for sample in samples],
    )
    metrics = summarize_generation_metrics(per_query)

    timestamp = datetime.now(tz=UTC).strftime("%Y%m%dT%H%M%SZ")
    output_dir = args.output_dir or Path("evaluation/generation/results") / timestamp
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "metrics.json").write_text(
        json.dumps(metrics_to_json(metrics), indent=2),
        encoding="utf-8",
    )
    (output_dir / "comparison.md").write_text(
        render_generation_comparison_markdown(metrics),
        encoding="utf-8",
    )
    (output_dir / "quality_note.md").write_text(
        render_quality_note(metrics) + "\n",
        encoding="utf-8",
    )
    print(f"Wrote generation evaluation artifacts to {output_dir}")
    return 0


def main() -> int:
    args = _parse_args()
    return asyncio.run(_run_evaluation(args))


if __name__ == "__main__":
    raise SystemExit(main())
