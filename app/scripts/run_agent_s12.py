#!/usr/bin/env python3
"""Session 12 — run the hand-written estimation agent over a transcript."""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from app.config import get_settings
from app.database import get_session_factory, reset_session_factory
from app.embedding_pipeline.chunk_content_repository import ChunkContentRepository
from app.embedding_pipeline.embedder import OpenAIEmbedder
from app.embedding_pipeline.lexical_search_repository import LexicalSearchRepository
from app.embedding_pipeline.rerank import build_reranker
from app.embedding_pipeline.retrieval_service import RetrievalService
from app.embedding_pipeline.search_repository import SemanticSearchRepository
from app.services.agentic.agent_loop import run_estimation_agent
from app.services.agentic.agent_schemas import AgentRunResult
from app.services.agentic.openai_client import get_async_openai_client
from app.services.agentic.retrieval_adapter import build_retrieval_backend, load_stub_retrieval_backend


def _render(result: AgentRunResult) -> str:
    lines = [
        "=" * 78,
        "AGENT TRACE",
        "=" * 78,
        result.trace.render(),
        "",
        "=" * 78,
        f"FINAL ESTIMATE  (iterations={result.iterations}, stopped={result.stopped_reason})",
        "=" * 78,
    ]
    estimate = result.estimate
    if estimate is None:
        lines.append("(the agent stopped without producing a structured estimate)")
        return "\n".join(lines)

    for component in estimate.components:
        cited = ", ".join(str(chunk_id) for chunk_id in component.cited_chunk_ids) or "none"
        lines.append(f"  - {component.name}: {component.estimated_hours}h  [sources: {cited}]")
        lines.append(f"      {component.rationale}")
    lines.append("")
    lines.append(f"  TOTAL: {estimate.total_hours}h    confidence: {estimate.confidence}")
    if estimate.assumptions:
        lines.append("  assumptions:")
        for assumption in estimate.assumptions:
            lines.append(f"    · {assumption}")
    return "\n".join(lines)


async def _main_async(args: argparse.Namespace) -> int:
    transcript_path = Path(args.transcript)
    if not transcript_path.is_file():
        print(f"ERROR: transcript not found: {transcript_path}", file=sys.stderr)
        return 1

    settings = get_settings()
    client = get_async_openai_client(settings)
    if client is None:
        print(
            "ERROR: OPENAI_API_KEY is not set — the agent needs the OpenAI Responses API.",
            file=sys.stderr,
        )
        return 1

    transcript = transcript_path.read_text(encoding="utf-8")

    if args.stub:
        backend_name = "stub"
        backend = load_stub_retrieval_backend()
        result = await run_estimation_agent(
            transcript,
            client=client,
            model=args.model,
            reasoning_effort=args.effort,
            max_iterations=args.max_iterations,
            retrieval_backend=backend,
        )
    elif not settings.database_url.strip():
        print(
            "ERROR: DATABASE_URL is not set. Use --stub for offline debugging.",
            file=sys.stderr,
        )
        return 1
    else:
        backend_name = "retrieval pipeline"
        reset_session_factory()
        session_factory = get_session_factory(settings)
        retrieval_service = RetrievalService()
        embedder = OpenAIEmbedder(settings)
        reranker = build_reranker(settings)
        async with session_factory() as session:
            backend = build_retrieval_backend(
                session=session,
                embedder=embedder,
                reranker=reranker,
                settings=settings,
                retrieval_service=retrieval_service,
                content_repository=ChunkContentRepository(),
                vector_repository=SemanticSearchRepository(),
                lexical_repository=LexicalSearchRepository(
                    text_search_config=settings.retrieval_lexical_text_search_config,
                ),
            )
            result = await run_estimation_agent(
                transcript,
                client=client,
                model=args.model,
                reasoning_effort=args.effort,
                max_iterations=args.max_iterations,
                retrieval_backend=backend,
            )

    print(f"transcript : {transcript_path}")
    print(f"model      : {args.model}   effort: {args.effort}   backend: {backend_name}")
    print()

    rendered = _render(result)
    print(rendered)

    if args.out:
        Path(args.out).write_text(rendered + "\n", encoding="utf-8")
        print(f"\n(trace written to {args.out})")
    return 0


def main() -> int:
    settings = get_settings()
    parser = argparse.ArgumentParser(description="Run the Session 12 estimation agent.")
    parser.add_argument("transcript", help="Path to a meeting transcript .txt file.")
    parser.add_argument(
        "--model",
        default=settings.agent_model,
        help=f"OpenAI model (default {settings.agent_model}).",
    )
    parser.add_argument(
        "--effort",
        default=settings.agent_reasoning_effort,
        choices=["minimal", "low", "medium", "high"],
        help="Reasoning effort for the Responses API.",
    )
    parser.add_argument(
        "--max-iterations",
        type=int,
        default=settings.agent_max_iterations,
        help="Loop safeguard: max Responses API round-trips.",
    )
    parser.add_argument(
        "--stub",
        action="store_true",
        help="Use the offline reference retrieval stub (no database).",
    )
    parser.add_argument("--out", help="Write the rendered trace + estimate to this file.")
    args = parser.parse_args()
    return asyncio.run(_main_async(args))


if __name__ == "__main__":
    raise SystemExit(main())
