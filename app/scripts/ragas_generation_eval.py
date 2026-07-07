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
    BaselineParseError,
    RagasSample,
    build_ragas_records,
    coherence_gate_exit_code,
    coherence_gate_result_to_json,
    evaluate_coherence_gate,
    evaluate_gate,
    extract_per_query_metrics,
    format_ragas_answer,
    gate_exit_code,
    gate_result_to_json,
    load_baseline,
    load_generation_golden_set,
    metrics_to_json,
    render_coherence_gate_summary,
    render_gate_summary,
    render_generation_comparison_markdown,
    render_monitor_summary,
    render_quality_note,
    run_ragas_evaluation,
    summarize_generation_metrics,
    validate_generation_preflight,
)
from app.embedding_pipeline.retrieval_eval import fetch_alembic_revision, fetch_corpus_snapshot
from app.embedding_pipeline.rerank import build_reranker
from app.embedding_pipeline.retrieval_service import RetrievalService, parse_retrieval_mode
from app.services.llm_chain import build_provider_chain
from app.services.rag_estimation_service import RagEstimationService


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
    parser.add_argument(
        "--gate",
        action="store_true",
        help=(
            "Compare aggregate metrics against the committed baseline and exit "
            "1 on regression (see --baseline / --tolerance)."
        ),
    )
    parser.add_argument(
        "--coherence-gate",
        action="store_true",
        help=(
            "When used with --gate, also fail if any golden-set estimate reports "
            "structural coherence violations."
        ),
    )
    parser.add_argument(
        "--monitor",
        action="store_true",
        help="Print a one-line faithfulness/answer relevancy summary (no exit code impact).",
    )
    parser.add_argument(
        "--baseline",
        type=Path,
        default=Path("evaluation/generation/RAGAS_BASELINE.md"),
        help="Baseline Markdown file used by --gate.",
    )
    parser.add_argument(
        "--tolerance",
        type=float,
        default=None,
        help="Override the tolerance documented in the baseline file.",
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
    coherence_violation_count = 0
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
            if outcome.coherence_report.has_violations:
                coherence_violation_count += 1
            samples.append(
                RagasSample(
                    query_id=golden.id,
                    question=golden.question,
                    answer=format_ragas_answer(outcome.result),
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

    if args.monitor:
        print(render_monitor_summary(metrics))

    exit_code = 0
    metrics_json = metrics_to_json(metrics)
    metrics_json["coherence_violation_count"] = coherence_violation_count
    if args.gate:
        try:
            baseline = load_baseline(args.baseline)
        except BaselineParseError as exc:
            print(str(exc), file=sys.stderr)
            return 2
        gate_result = evaluate_gate(metrics, baseline, tolerance=args.tolerance)
        print(render_gate_summary(gate_result))
        metrics_json["gate_result"] = gate_result_to_json(gate_result)
        exit_code = gate_exit_code(gate_result)
        if args.coherence_gate:
            coherence_gate_result = evaluate_coherence_gate(coherence_violation_count)
            print(render_coherence_gate_summary(coherence_gate_result))
            metrics_json["coherence_gate_result"] = coherence_gate_result_to_json(
                coherence_gate_result
            )
            if coherence_gate_exit_code(coherence_gate_result) != 0:
                exit_code = 1

    timestamp = datetime.now(tz=UTC).strftime("%Y%m%dT%H%M%SZ")
    output_dir = args.output_dir or Path("evaluation/generation/results") / timestamp
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "metrics.json").write_text(
        json.dumps(metrics_json, indent=2),
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
    return exit_code


def main() -> int:
    args = _parse_args()
    return asyncio.run(_run_evaluation(args))


if __name__ == "__main__":
    raise SystemExit(main())
