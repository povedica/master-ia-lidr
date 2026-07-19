#!/usr/bin/env python3
"""Session 13 — run the multi-agent estimation graph end to end.

Drives the compiled LangGraph ``StateGraph`` (``app.services.estimation_graph``)
through the full agent pipeline, AUTO-APPROVING the two human gates so a whole
run completes without a person in the loop:

    classifier_agent → structure_agent → [HUMAN GATE 1] → estimate_task_hours × N
      → recover_and_handover → analysis_agent → [HUMAN GATE 2] → proposal_agent

Each ``interrupt()`` pauses the graph; this script resumes it with a canned
``Command(resume=...)`` (accept the structure at gate 1; validate + ask for a
proposal at gate 2). In production the HTTP resume endpoints (feature-066 Step 6)
supply those decisions from the UI.

Persistence:

* Default: Postgres checkpointer via ``open_checkpointer()`` (feature-066 Step 5).
* ``--memory``: in-process ``MemorySaver`` (no database for checkpoints).

``--stub`` swaps the real per-task hours retrieval (``estimate_one``) for a canned
offline estimate so the fan-out needs no database. The real path needs the
historical-task corpus ingested and a working ``estimate_one`` binding.

Run variants::

    # Partial-offline smoke: no DB, canned per-task hours (still needs OPENAI_API_KEY
    # for the classifier / structure / analysis / proposal agents)
    uv run python app/scripts/run_graph_s13.py --memory --stub

    # Full path (Postgres checkpointer + real task-hours retrieval) — needs Step 5
    uv run python app/scripts/run_graph_s13.py \\
        --out exercises/session-13/example_run_complex.txt
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from langgraph.types import Command

from app.schemas.rag_task_hours import TaskHoursEstimateView
from app.services.estimation_graph.build import build_graph

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_TRANSCRIPT = (
    REPO_ROOT / "exercises" / "session-13" / "sample_transcript_complex.txt"
)

# Canned resume decisions the runner feeds at each gate (auto-approval).
GATE_DECISIONS = {
    "structure_review": {"approved": True},
    "final_review": {"validated": True, "want_proposal": True},
}


def install_stub_hours() -> None:
    """Monkeypatch per-task hours retrieval with a canned offline estimate.

    Keeps the fan-out DB-free: every task gets a deterministic grounded estimate, so
    no task is flagged and the recovery loop never runs.
    """
    from app.services.estimation_graph.agents import hours as hours_mod

    async def _stub_estimate_one(
        module: str,
        name: str,
        description: str | None,
        *,
        top_k: int,
        distance_threshold: float,
        **kwargs: object,
    ) -> TaskHoursEstimateView:
        del description, top_k, distance_threshold, kwargs
        hours = 8 + (abs(hash((module, name))) % 10) * 8  # 8..80h
        return TaskHoursEstimateView(
            module=module,
            task=name,
            estimated_hours=hours,
            reliability=0.82,
            has_match=True,
            dispersion=0.1,
            neighbors=[],
        )

    hours_mod.estimate_one = _stub_estimate_one  # type: ignore[assignment]


def render_run(state: dict) -> str:
    """Render a completed graph state as a human-readable run report."""
    lines = [
        "=" * 78,
        "SESSION 13 — MULTI-AGENT ESTIMATION GRAPH RUN",
        "=" * 78,
        f"estimation_id : {state.get('estimation_id')}",
        f"complexity    : {state.get('complexity')}",
        f"status        : {state.get('status')}",
        "",
        "STRUCTURE (structure_agent → gate 1)",
    ]
    for module in (state.get("structure") or {}).get("modules") or []:
        lines.append(f"  ▸ {module.get('name')}")
        for task in module.get("tasks") or []:
            lines.append(f"      - {task.get('name')}")

    lines += ["", "ESTIMATE (hours agent → analysis → gate 2)"]
    estimate = state.get("estimate") or {}
    for module in estimate.get("modules") or []:
        lines.append(f"  ▸ {module.get('name')}")
        for task in module.get("tasks") or []:
            hours = task.get("estimated_hours")
            hours_text = f"{hours}h" if hours is not None else "NO MATCH"
            flag = "" if task.get("has_match") else "  ⚠ flagged"
            lines.append(f"      - {task.get('name')}: {hours_text}{flag}")
    lines.append(
        f"  TOTAL: {estimate.get('total_engineer_days')}d "
        f"({estimate.get('total_engineer_hours')}h, confidence {estimate.get('confidence')})"
    )

    report = state.get("analysis_report") or {}
    lines += ["", "RELIABILITY REPORT (analysis_agent)"]
    lines.append(f"  overall_confidence : {report.get('overall_confidence')}")
    lines.append(f"  grounded_task_ratio: {report.get('grounded_task_ratio')}")
    for weak in report.get("weak_points") or []:
        lines.append(f"  - [{weak.get('severity')}] {weak.get('area')}: {weak.get('issue')}")
    if report.get("summary"):
        lines.append(f"  summary: {report.get('summary')}")

    proposal = state.get("proposal")
    if proposal:
        lines += ["", "COMMERCIAL PROPOSAL (proposal_agent — bonus)", str(proposal)]

    errors = state.get("errors") or []
    if errors:
        lines += ["", "ERRORS / ISSUES"]
        lines += [f"  - {e}" for e in errors]
    return "\n".join(lines)


async def run_to_completion(graph, transcript: str, estimation_id: str) -> dict:
    """Start the run and auto-approve every human gate until it completes."""
    config = {"configurable": {"thread_id": estimation_id}}
    await graph.ainvoke(
        {"transcript": transcript, "estimation_id": estimation_id},
        config,
    )

    while True:
        snapshot = await graph.aget_state(config)
        if not snapshot.next:
            return snapshot.values  # completed
        interrupts = snapshot.interrupts or ()
        if not interrupts:
            await graph.ainvoke(None, config)
            continue
        gate = (interrupts[0].value or {}).get("gate", "")
        decision = GATE_DECISIONS.get(gate, {"approved": True, "validated": True})
        print(f"  ⏸ human gate '{gate}' → auto-resume {decision}")
        await graph.ainvoke(Command(resume=decision), config)


def _resolve_open_checkpointer():
    """Return ``open_checkpointer`` when Step 5 has wired it; else ``None``."""
    from app.services.estimation_graph import checkpointer as checkpointer_mod

    return getattr(checkpointer_mod, "open_checkpointer", None)


async def _main_async(args: argparse.Namespace) -> int:
    transcript_path = Path(args.transcript)
    if not transcript_path.is_file():
        print(f"ERROR: transcript not found: {transcript_path}", file=sys.stderr)
        return 1
    transcript = transcript_path.read_text(encoding="utf-8")
    estimation_id = args.estimation_id or f"s13-{transcript_path.stem}"

    if args.stub:
        install_stub_hours()

    print(f"transcript    : {transcript_path}")
    print(f"checkpointer  : {'MemorySaver' if args.memory else 'AsyncPostgresSaver (pool)'}")
    print(f"per-task hours: {'stub (offline)' if args.stub else 'real estimate_one()'}")
    print(f"estimation_id : {estimation_id}\n")

    if args.memory:
        from langgraph.checkpoint.memory import MemorySaver

        graph = build_graph(MemorySaver())
        state = await run_to_completion(graph, transcript, estimation_id)
    else:
        open_checkpointer = _resolve_open_checkpointer()
        if open_checkpointer is None:
            print(
                "ERROR: Postgres checkpointer is not wired yet "
                "(feature-066 Step 5: open_checkpointer). Use --memory for offline runs.",
                file=sys.stderr,
            )
            return 1
        async with open_checkpointer() as checkpointer:
            graph = build_graph(checkpointer)
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
        description="Run the Session 13 multi-agent estimation graph."
    )
    parser.add_argument(
        "--transcript",
        default=str(DEFAULT_TRANSCRIPT),
        help="Path to a meeting transcript .txt (default: session-13 complex RUTA).",
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
        help="Use canned offline per-task hours (no database for the fan-out).",
    )
    parser.add_argument("--out", help="Write the rendered run to this file.")
    args = parser.parse_args()
    return asyncio.run(_main_async(args))


if __name__ == "__main__":
    raise SystemExit(main())
