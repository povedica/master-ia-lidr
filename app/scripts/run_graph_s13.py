#!/usr/bin/env python3
"""Session 14 — run the supervisor/worker estimation graph end to end.

Drives the compiled LangGraph ``StateGraph`` through the supervisor/workers
pipeline. When conditional HITL pauses at ``estimation_review``, this script
auto-resumes with a canned approve decision (override via ``GATE_DECISIONS``).

Persistence:

* Default: Postgres checkpointer via ``open_checkpointer()``.
* ``--memory``: in-process ``MemorySaver`` (no database for checkpoints).

``--stub`` injects offline worker dependencies (no live retrieval / LLM).

Run variants::

    uv run python app/scripts/run_graph_s13.py --memory --stub

    uv run python app/scripts/run_graph_s13.py \\
        --transcript exercises/session-14/sample_transcript_edge_case.txt \\
        --out /tmp/supervisor_hitl_edge_case_trace.txt
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path
from typing import Any

from langgraph.types import Command

from app.services.estimation_graph.build import build_graph
from app.services.estimation_graph.schemas import (
    ExtractedRequirement,
    ExtractedRequirements,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_TRANSCRIPT = (
    REPO_ROOT / "exercises" / "session-14" / "sample_transcript_edge_case.txt"
)
LEGACY_TRANSCRIPT = (
    REPO_ROOT / "exercises" / "session-13" / "sample_transcript_complex.txt"
)

# Canned resume decisions the runner feeds at each interrupt (auto-approval).
GATE_DECISIONS = {
    "estimation_review": {
        "action": "approve",
        "comment": "CLI auto-approve for offline / smoke runs.",
    },
}


async def _stub_complete(**kwargs: Any) -> ExtractedRequirements:
    del kwargs
    return ExtractedRequirements(
        requirements=[
            ExtractedRequirement(
                id="req-1",
                text="Quantum logistics teleportation dashboard",
                category="r&d",
            ),
            ExtractedRequirement(
                id="req-2",
                text="Legacy ERP holographic bridge",
                category="integration",
            ),
        ]
    )


async def _stub_search(raw_args: dict[str, Any], *, backend: Any = None) -> dict[str, Any]:
    del raw_args, backend
    return {"items": [], "count": 0, "summary": "no historical items"}


def _stub_calculate(raw_args: dict[str, Any]) -> dict[str, Any]:
    components = []
    for component in raw_args.get("components") or []:
        refs = component.get("reference_amounts") or []
        hours = round(float(refs[0]) * 1.15, 1) if refs else 0.0
        components.append(
            {
                "name": component["name"],
                "reference_count": len(refs),
                "estimated_hours": hours,
                "unbudgeted": not refs,
            }
        )
    total = round(sum(row["estimated_hours"] for row in components), 1)
    return {
        "components": components,
        "total_hours": total,
        "contingency_factor": 0.15,
        "summary": f"total={total}h",
    }


def _stub_validate(raw_args: dict[str, Any]) -> dict[str, Any]:
    issues = [
        f"{component['name']!r} has no historical reference (unbudgeted)."
        for component in raw_args.get("components") or []
        if not component.get("reference_amounts")
    ]
    return {
        "ok": not issues,
        "issues": issues,
        "summary": "ok" if not issues else f"{len(issues)} issue(s) found",
    }


def install_stub_workers() -> dict[str, Any]:
    """Return injectable offline worker dependencies for ``build_graph``."""
    return {
        "complete_fn": _stub_complete,
        "search_budgets_fn": _stub_search,
        "calculate_estimate_fn": _stub_calculate,
        "validate_estimate_fn": _stub_validate,
        "confidence_threshold": 0.70,
    }


# Backward-compatible alias used by older tests/docs.
def install_stub_hours() -> None:
    """Deprecated S13 hook; Session 14 stubs are installed via ``install_stub_workers``."""
    return None


def render_run(state: dict) -> str:
    """Render a completed graph state as a human-readable run report."""
    lines = [
        "=" * 78,
        "SESSION 14 — SUPERVISOR/WORKER ESTIMATION GRAPH RUN",
        "=" * 78,
        f"estimation_id : {state.get('estimation_id')}",
        f"status        : {state.get('status')}",
        f"confidence    : {state.get('confidence')}",
        f"last_route    : {state.get('last_route')}",
        f"route_reason  : {state.get('route_reason')}",
        "",
        "REQUIREMENTS",
    ]
    for requirement in state.get("requirements") or []:
        if isinstance(requirement, dict):
            lines.append(
                f"  ▸ {requirement.get('id')}: {requirement.get('text')} "
                f"[{requirement.get('category')}]"
            )
        else:
            lines.append(f"  ▸ {requirement}")

    lines += ["", "BUDGET MATCHES"]
    for match in state.get("budget_matches") or []:
        marker = "NO MATCH" if match.get("no_match") else match.get("reference_budget_id")
        lines.append(
            f"  ▸ {match.get('requirement_id')}: {marker} "
            f"({match.get('amount')}h, d={match.get('distance')})"
        )

    estimate = state.get("estimate") or {}
    lines += ["", "ESTIMATE"]
    for component in estimate.get("components") or []:
        flag = " ⚠ unbudgeted" if component.get("unbudgeted") else ""
        lines.append(
            f"  ▸ {component.get('name')}: {component.get('estimated_hours')}h{flag}"
        )
    lines.append(f"  TOTAL: {estimate.get('total_hours')}h")

    validation = state.get("validation") or {}
    lines += ["", "VALIDATION"]
    lines.append(f"  ok            : {validation.get('ok')}")
    lines.append(f"  no_precedent  : {validation.get('no_precedent')}")
    lines.append(f"  out_of_range  : {validation.get('out_of_historical_range')}")
    for reason in validation.get("review_reasons") or []:
        lines.append(f"  - reason: {reason}")

    resolution = state.get("human_resolution")
    if resolution:
        lines += ["", "HUMAN RESOLUTION", f"  {resolution}"]

    decisions = state.get("supervisor_decisions") or []
    if decisions:
        lines += ["", "SUPERVISOR DECISIONS"]
        for decision in decisions:
            lines.append(f"  → {decision.get('goto')} ({decision.get('reason')})")

    errors = state.get("errors") or []
    if errors:
        lines += ["", "ERRORS / ISSUES"]
        lines += [f"  - {error}" for error in errors]
    return "\n".join(lines)


async def run_to_completion(graph, transcript: str, estimation_id: str) -> dict:
    """Start the run and auto-resolve every human interrupt until it completes."""
    config = {"configurable": {"thread_id": estimation_id}}
    await graph.ainvoke(
        {
            "transcript": transcript,
            "estimation_id": estimation_id,
            "status": "running",
        },
        config,
    )

    while True:
        snapshot = await graph.aget_state(config)
        if not snapshot.next:
            return snapshot.values
        interrupts = snapshot.interrupts or ()
        if not interrupts:
            await graph.ainvoke(None, config)
            continue
        gate = (interrupts[0].value or {}).get("gate", "")
        decision = GATE_DECISIONS.get(
            gate,
            {"action": "approve", "comment": "CLI default approve"},
        )
        print(f"  ⏸ human gate '{gate}' → auto-resume {decision}")
        await graph.ainvoke(Command(resume=decision), config)


def _resolve_open_checkpointer():
    from app.services.estimation_graph import checkpointer as checkpointer_mod

    return getattr(checkpointer_mod, "open_checkpointer", None)


def _default_transcript_path() -> Path:
    if DEFAULT_TRANSCRIPT.is_file():
        return DEFAULT_TRANSCRIPT
    return LEGACY_TRANSCRIPT


async def _main_async(args: argparse.Namespace) -> int:
    transcript_path = Path(args.transcript)
    if not transcript_path.is_file():
        print(f"ERROR: transcript not found: {transcript_path}", file=sys.stderr)
        return 1
    transcript = transcript_path.read_text(encoding="utf-8")
    estimation_id = args.estimation_id or f"s14-{transcript_path.stem}"

    build_kwargs: dict[str, Any] = {}
    if args.stub:
        build_kwargs.update(install_stub_workers())

    print(f"transcript    : {transcript_path}")
    print(f"checkpointer  : {'MemorySaver' if args.memory else 'AsyncPostgresSaver (pool)'}")
    print(f"workers       : {'stub (offline)' if args.stub else 'live dependencies'}")
    print(f"estimation_id : {estimation_id}\n")

    if args.memory:
        from langgraph.checkpoint.memory import MemorySaver

        graph = build_graph(MemorySaver(), **build_kwargs)
        state = await run_to_completion(graph, transcript, estimation_id)
    else:
        open_checkpointer = _resolve_open_checkpointer()
        if open_checkpointer is None:
            print(
                "ERROR: Postgres checkpointer is not wired. Use --memory for offline runs.",
                file=sys.stderr,
            )
            return 1
        async with open_checkpointer() as checkpointer:
            graph = build_graph(checkpointer, **build_kwargs)
            state = await run_to_completion(graph, transcript, estimation_id)

    rendered = render_run(state)
    print("\n" + rendered)
    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(rendered + "\n", encoding="utf-8")
        print(f"\n(run written to {args.out})")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run the Session 14 supervisor/worker estimation graph."
    )
    parser.add_argument(
        "--transcript",
        default=str(_default_transcript_path()),
        help="Path to a meeting transcript .txt.",
    )
    parser.add_argument(
        "--estimation-id",
        help="thread_id for the checkpointer (default derived from transcript stem).",
    )
    parser.add_argument(
        "--memory",
        action="store_true",
        help="Use an in-process MemorySaver instead of the Postgres checkpointer.",
    )
    parser.add_argument(
        "--stub",
        action="store_true",
        help="Inject offline worker fakes (no live LLM/retrieval).",
    )
    parser.add_argument("--out", help="Write the rendered run to this file.")
    args = parser.parse_args()
    return asyncio.run(_main_async(args))


if __name__ == "__main__":
    raise SystemExit(main())
