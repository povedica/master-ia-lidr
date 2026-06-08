"""Generate Markdown stress report tables from results.csv."""

from __future__ import annotations

import csv
import statistics
from collections import defaultdict
from pathlib import Path
from typing import Any


def percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    rank = (len(ordered) - 1) * (pct / 100.0)
    lower = int(rank)
    upper = min(lower + 1, len(ordered) - 1)
    weight = rank - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


def load_rows(csv_path: Path) -> list[dict[str, str]]:
    with csv_path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def write_report(csv_path: Path, output_path: Path) -> None:
    rows = load_rows(csv_path)
    if not rows:
        output_path.write_text("# CAG Stress Report\n\nNo rows in CSV.\n", encoding="utf-8")
        return

    summary = _summary_table(rows)
    curve_latency_tokens = _curve_latency_vs_tokens(rows)
    curve_cost_turn = _curve_cost_vs_turn(rows)
    curve_drift_n = _curve_drift_vs_n(rows)
    interpretation = _interpretation_paragraphs(rows)

    content = "\n".join(
        [
            "# CAG Stress Report",
            "",
            "Generated from `{csv}`.".format(csv=csv_path.as_posix()),
            "",
            "## Summary",
            "",
            summary,
            "",
            "## Curve 1 — latency_ms vs tokens_in",
            "",
            curve_latency_tokens,
            "",
            "## Curve 2 — cumulative cost_usd vs turn_index",
            "",
            curve_cost_turn,
            "",
            "## Curve 3 — mean memory drift vs N (turn count)",
            "",
            curve_drift_n,
            "",
            "## Interpretation",
            "",
            interpretation,
            "",
        ]
    )
    output_path.write_text(content, encoding="utf-8")


def _summary_table(rows: list[dict[str, str]]) -> str:
    groups: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        key = (row.get("scenario_name", ""), row.get("attachment_size_kb", ""))
        groups[key].append(row)

    headers = [
        "scenario",
        "attachment_kb",
        "p50_latency_ms",
        "p95_latency_ms",
        "total_cost_usd",
        "exact_cache_hit_rate",
        "semantic_cache_hit_rate",
        "mean_memory_drift",
    ]
    body: list[list[str]] = []
    for (scenario, attachment_kb), group in sorted(groups.items()):
        latencies = [_float(row.get("latency_ms")) for row in group]
        costs = [_float(row.get("cost_usd")) for row in group]
        exact_hits = [1.0 if row.get("cache_hit_kind") == "exact" else 0.0 for row in group]
        semantic_hits = [1.0 if row.get("cache_hit_kind") == "semantic" else 0.0 for row in group]
        drift_scores = [_float(row.get("metric_memory_drift_score")) for row in group]
        body.append(
            [
                scenario,
                attachment_kb,
                f"{percentile(latencies, 50):.0f}",
                f"{percentile(latencies, 95):.0f}",
                f"{sum(costs):.4f}",
                f"{statistics.fmean(exact_hits):.2f}",
                f"{statistics.fmean(semantic_hits):.2f}",
                f"{statistics.fmean(drift_scores):.2f}",
            ]
        )
    return _markdown_table(headers, body)


def _curve_latency_vs_tokens(rows: list[dict[str, str]]) -> str:
    headers = ["tokens_in", "latency_ms", "scenario_name", "turn_index"]
    body = [
        [
            row.get("tokens_in", ""),
            row.get("latency_ms", ""),
            row.get("scenario_name", ""),
            row.get("turn_index", ""),
        ]
        for row in sorted(rows, key=lambda item: (_float(item.get("tokens_in")), _float(item.get("latency_ms"))))
    ]
    return _markdown_table(headers, body[:40])


def _curve_cost_vs_turn(rows: list[dict[str, str]]) -> str:
    headers = ["scenario_name", "turn_index", "cumulative_cost_usd"]
    accum: dict[str, float] = defaultdict(float)
    body: list[list[str]] = []
    for row in sorted(rows, key=lambda item: (item.get("scenario_name", ""), _int(item.get("turn_index")))):
        scenario = row.get("scenario_name", "")
        accum[scenario] += _float(row.get("cost_usd"))
        body.append([scenario, row.get("turn_index", ""), f"{accum[scenario]:.4f}"])
    return _markdown_table(headers, body[:40])


def _curve_drift_vs_n(rows: list[dict[str, str]]) -> str:
    groups: dict[int, list[float]] = defaultdict(list)
    for row in rows:
        n_turns = _int(row.get("scenario_turn_count"))
        groups[n_turns].append(_float(row.get("metric_memory_drift_score")))
    headers = ["scenario_turn_count", "mean_memory_drift_score", "rows"]
    body = [
        [str(n), f"{statistics.fmean(scores):.2f}", str(len(scores))]
        for n, scores in sorted(groups.items())
    ]
    return _markdown_table(headers, body)


def _interpretation_paragraphs(rows: list[dict[str, str]]) -> str:
    by_turn: dict[int, list[float]] = defaultdict(list)
    latencies = [_float(row.get("latency_ms")) for row in rows]
    costs = [_float(row.get("cost_usd")) for row in rows]
    drift_scores = [_float(row.get("metric_memory_drift_score")) for row in rows]
    for row in rows:
        by_turn[_int(row.get("turn_index"))].append(_float(row.get("metric_memory_drift_score")))

    break_turn = 1
    for turn in sorted(by_turn):
        if statistics.fmean(by_turn[turn]) < 0.6:
            break_turn = turn
            break
    else:
        break_turn = max(by_turn) if by_turn else 1

    p95_latency = percentile(latencies, 95)
    total_cost = sum(costs)
    mean_drift = statistics.fmean(drift_scores) if drift_scores else 0.0
    max_cost_row = max(rows, key=lambda row: _float(row.get("cost_usd")), default={})
    min_cost_row = min(rows, key=lambda row: _float(row.get("cost_usd")), default={})
    cost_ratio = (
        _float(max_cost_row.get("cost_usd")) / _float(min_cost_row.get("cost_usd"))
        if _float(min_cost_row.get("cost_usd")) > 0
        else 0.0
    )

    dominant = "latency"
    if total_cost > 0 and mean_drift < 0.5 and p95_latency < 4000:
        dominant = "memory loss"
    elif total_cost > 0 and p95_latency < 4000 and mean_drift >= 0.5:
        dominant = "cost"

    paragraph_one = (
        f"Across {len(rows)} observed turns, mean memory drift is {mean_drift:.2f} and "
        f"recall falls below 0.60 from turn {break_turn} onward in this run. "
        f"P95 latency reaches {p95_latency:.0f} ms while per-turn cost spreads up to "
        f"{cost_ratio:.1f}x between the cheapest and most expensive turn."
    )
    paragraph_two = (
        f"The dominant degradation dimension in this dataset is {dominant}. "
        f"Total observed spend is ${total_cost:.4f} with semantic cache hits at "
        f"{statistics.fmean([1.0 if row.get('cache_hit_kind') == 'semantic' else 0.0 for row in rows]):.2f}. "
        "A RAG boundary is justified when turn depth routinely exceeds the window while "
        f"memory drift stays under 0.60 at N>={break_turn} despite stable latency budgets."
    )
    return paragraph_one + "\n\n" + paragraph_two


def _markdown_table(headers: list[str], rows: list[list[str]]) -> str:
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join(["---"] * len(headers)) + " |",
    ]
    for row in rows:
        lines.append("| " + " | ".join(row) + " |")
    return "\n".join(lines)


def _float(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _int(value: Any) -> int:
    try:
        return int(float(value or 0))
    except (TypeError, ValueError):
        return 0
