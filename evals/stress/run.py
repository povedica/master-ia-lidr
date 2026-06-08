"""CLI runner for CAG stress scenarios."""

from __future__ import annotations

import argparse
import asyncio
import csv
import io
import sys
from pathlib import Path
from typing import Any

import httpx
from httpx import ASGITransport, AsyncClient

from evals.stress.metrics import CostBudgetMetric, LatencyBudgetMetric, MemoryDriftMetric
from evals.stress.report import write_report
from evals.stress.scenarios import build_scenario, list_supported_turn_counts

FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures"
DEFAULT_OUTPUT = Path("evals/stress/results.csv")
DEFAULT_REPORT = Path("evals/stress/REPORT.md")


def scenario_artifact_path(base: Path, scenario_name: str) -> Path:
    """Derive per-scenario artifact path, e.g. results.csv -> results-pivot.csv."""

    return base.parent / f"{base.stem}-{scenario_name}{base.suffix}"
CSV_COLUMNS = [
    "scenario_name",
    "repeat_index",
    "attachment_size_kb",
    "scenario_turn_count",
    "turn_index",
    "session_id",
    "turn_index_observed",
    "session_id_observed",
    "enriched_transcript_chars",
    "attachments_total_chars",
    "messages_in_window",
    "anchors_count",
    "summary_chars",
    "tokens_in",
    "tokens_out",
    "cost_usd",
    "latency_ms",
    "cache_hit_kind",
    "last_resolved_tier",
    "metric_latency_budget_score",
    "metric_cost_budget_score",
    "metric_memory_drift_score",
    "fact_to_remember",
    "drift_evaluated_against_turn",
]


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run CAG stress scenarios and write CSV results.")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--http", metavar="URL", help="Base URL for a running uvicorn app.")
    mode.add_argument("--in-process", action="store_true", help="Run against in-process ASGI app.")
    parser.add_argument("--scenarios", default="growing,pivot,contradiction")
    parser.add_argument("--attachment-sizes", default="0,5,20,50,100")
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--turn-counts", default=",".join(str(value) for value in list_supported_turn_counts()))
    parser.add_argument(
        "--output",
        default=str(DEFAULT_OUTPUT),
        help="Base CSV path; each scenario writes results-<scenario>.csv beside this stem.",
    )
    parser.add_argument(
        "--write-report",
        action="store_true",
        help="Also generate REPORT-<scenario>.md beside the CSV for each scenario.",
    )
    parser.add_argument(
        "--report-output",
        default=str(DEFAULT_REPORT),
        help="Base report path; each scenario writes REPORT-<scenario>.md beside this stem.",
    )
    parser.add_argument("--latency-budget-ms", type=int, default=4000)
    parser.add_argument("--cost-budget-usd", type=float, default=0.05)
    return parser.parse_args(argv)


def _parse_csv_ints(raw: str) -> list[int]:
    return [int(item.strip()) for item in raw.split(",") if item.strip()]


def _attachment_path(size_kb: int) -> Path | None:
    if size_kb <= 0:
        return None
    return FIXTURE_DIR / f"attach_{size_kb}kb.pdf"


def _session_snapshot(detail: dict[str, Any]) -> dict[str, Any]:
    derived = detail.get("project_metadata") or {}
    return {
        "project_metadata": {},
        "last_derived_metadata": derived,
        "last_turn_observation": detail.get("last_turn_observation"),
    }


async def _submit_turn(
    client: AsyncClient,
    *,
    session_id: str,
    turn_index: int,
    transcript: str,
    attachment_path: Path | None,
) -> None:
    data: dict[str, str] = {"transcript": transcript}
    if turn_index == 1:
        data.update(
            {
                "project_name": "StressRun",
                "project_type": "web_saas",
                "target_audience": "b2b_smb",
            }
        )
    files = None
    if attachment_path is not None:
        content = attachment_path.read_bytes()
        files = [("attachments", (attachment_path.name, io.BytesIO(content), "application/pdf"))]
    response = await client.post(
        f"/api/v1/sessions/{session_id}/estimate",
        data=data,
        files=files,
    )
    if response.status_code != 200:
        raise RuntimeError(
            f"estimate failed for session {session_id} turn {turn_index}: "
            f"{response.status_code} {response.text}"
        )


def _write_scenario_csv(output_path: Path, rows: list[dict[str, Any]]) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


async def run_stress(args: argparse.Namespace) -> list[Path]:
    scenarios = [name.strip() for name in args.scenarios.split(",") if name.strip()]
    attachment_sizes = _parse_csv_ints(args.attachment_sizes)
    turn_counts = _parse_csv_ints(args.turn_counts)
    output_base = Path(args.output)
    report_base = Path(args.report_output)
    output_base.parent.mkdir(parents=True, exist_ok=True)

    latency_metric = LatencyBudgetMetric(args.latency_budget_ms)
    cost_metric = CostBudgetMetric(args.cost_budget_usd)
    written_outputs: list[Path] = []

    if args.in_process:
        from app.main import app

        transport = ASGITransport(app=app)
        client_cm: Any = AsyncClient(transport=transport, base_url="http://test", timeout=120.0)
    else:
        client_cm = AsyncClient(base_url=args.http.rstrip("/"), timeout=120.0)

    async with client_cm as client:
        for scenario_name in scenarios:
            rows_to_write: list[dict[str, Any]] = []
            for attachment_size_kb in attachment_sizes:
                attachment_path = _attachment_path(attachment_size_kb)
                if attachment_path is not None and not attachment_path.exists():
                    raise FileNotFoundError(
                        f"missing fixture {attachment_path}; run "
                        "`uv run python -m evals.stress.fixtures.build_pdfs` first."
                    )
                for repeat_index in range(1, args.repeats + 1):
                    for n_turns in turn_counts:
                        scenario = build_scenario(scenario_name, n_turns)
                        created = await client.post("/api/v1/sessions")
                        if created.status_code != 201:
                            raise RuntimeError(f"session create failed: {created.status_code}")
                        session_id = created.json()["session_id"]
                        turn_records: list[dict[str, Any]] = []

                        for turn in scenario.turns:
                            await _submit_turn(
                                client,
                                session_id=session_id,
                                turn_index=turn.turn_index,
                                transcript=turn.transcript,
                                attachment_path=attachment_path,
                            )
                            detail = await client.get(f"/api/v1/sessions/{session_id}")
                            if detail.status_code != 200:
                                raise RuntimeError(f"session detail failed: {detail.status_code}")
                            payload = detail.json()
                            observation = payload.get("last_turn_observation") or {}
                            turn_records.append(
                                {
                                    "turn": turn,
                                    "observation": observation,
                                    "snapshot": _session_snapshot(payload),
                                }
                            )

                        final_turn_index = scenario.turns[-1].turn_index
                        final_snapshot = turn_records[-1]["snapshot"]
                        for record in turn_records:
                            turn = record["turn"]
                            observation = record["observation"]
                            latency_result = latency_metric.evaluate(observation)
                            cost_result = cost_metric.evaluate(observation)
                            drift_result = MemoryDriftMetric(turn.fact_to_remember).evaluate(final_snapshot)
                            rows_to_write.append(
                                {
                                    "scenario_name": scenario_name,
                                    "repeat_index": repeat_index,
                                    "attachment_size_kb": attachment_size_kb,
                                    "scenario_turn_count": n_turns,
                                    "turn_index": turn.turn_index,
                                    "session_id": session_id,
                                    "turn_index_observed": observation.get("turn_index"),
                                    "session_id_observed": observation.get("session_id"),
                                    "enriched_transcript_chars": observation.get("enriched_transcript_chars"),
                                    "attachments_total_chars": observation.get("attachments_total_chars"),
                                    "messages_in_window": observation.get("messages_in_window"),
                                    "anchors_count": observation.get("anchors_count"),
                                    "summary_chars": observation.get("summary_chars"),
                                    "tokens_in": observation.get("tokens_in"),
                                    "tokens_out": observation.get("tokens_out"),
                                    "cost_usd": observation.get("cost_usd"),
                                    "latency_ms": observation.get("latency_ms"),
                                    "cache_hit_kind": observation.get("cache_hit_kind"),
                                    "last_resolved_tier": observation.get("last_resolved_tier"),
                                    "metric_latency_budget_score": latency_result.score,
                                    "metric_cost_budget_score": cost_result.score,
                                    "metric_memory_drift_score": drift_result.score,
                                    "fact_to_remember": turn.fact_to_remember,
                                    "drift_evaluated_against_turn": final_turn_index,
                                }
                            )

            scenario_output = scenario_artifact_path(output_base, scenario_name)
            _write_scenario_csv(scenario_output, rows_to_write)
            written_outputs.append(scenario_output)
            if args.write_report:
                scenario_report = scenario_artifact_path(report_base, scenario_name)
                write_report(scenario_output, scenario_report)
                written_outputs.append(scenario_report)

    return written_outputs


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        outputs = asyncio.run(run_stress(args))
    except FileNotFoundError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except RuntimeError as exc:
        message = str(exc)
        print(message, file=sys.stderr)
        if "401" in message or "authentication" in message.lower():
            print("Ensure OPENAI_API_KEY is configured for HTTP stress runs.", file=sys.stderr)
        return 1
    for output in outputs:
        if output.suffix.lower() == ".csv":
            row_count = sum(1 for _ in output.open(encoding="utf-8")) - 1
            print(f"wrote {output} ({output.stat().st_size} bytes, {row_count} rows)")
        else:
            print(f"wrote {output} ({output.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
