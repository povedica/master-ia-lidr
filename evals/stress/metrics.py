"""Deterministic stress metrics for per-turn observations and session snapshots."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class MetricResult:
    name: str
    score: float
    passed: bool
    details: dict[str, Any]


class LatencyBudgetMetric:
    """Pass when ``latency_ms`` is within the configured budget."""

    def __init__(self, budget_ms: int) -> None:
        self._budget_ms = budget_ms

    def evaluate(self, observation: dict[str, Any]) -> MetricResult:
        latency_ms = int(observation.get("latency_ms") or 0)
        passed = latency_ms <= self._budget_ms
        return MetricResult(
            name="latency_budget",
            score=1.0 if passed else 0.0,
            passed=passed,
            details={"latency_ms": latency_ms, "budget_ms": self._budget_ms},
        )


class CostBudgetMetric:
    """Pass when ``cost_usd`` is within the configured budget."""

    def __init__(self, budget_usd: float) -> None:
        self._budget_usd = budget_usd

    def evaluate(self, observation: dict[str, Any]) -> MetricResult:
        cost_raw = observation.get("cost_usd")
        cost_usd = float(cost_raw) if cost_raw is not None else None
        passed = cost_usd is not None and cost_usd <= self._budget_usd
        return MetricResult(
            name="cost_budget",
            score=1.0 if passed else 0.0,
            passed=passed,
            details={"cost_usd": cost_usd, "budget_usd": self._budget_usd},
        )


class MemoryDriftMetric:
    """Pass when a tracked fact appears in an allowed snapshot location."""

    def __init__(self, fact: str, where: list[str] | None = None) -> None:
        self._fact = fact.strip().lower()
        self._where = where or ["summary", "anchors", "metadata"]

    def evaluate(self, session_snapshot: dict[str, Any]) -> MetricResult:
        matched_locations: list[str] = []
        for location in self._where:
            haystack = _location_text(session_snapshot, location)
            if self._fact and self._fact in haystack.lower():
                matched_locations.append(location)
        passed = bool(matched_locations)
        return MetricResult(
            name="memory_drift",
            score=1.0 if passed else 0.0,
            passed=passed,
            details={"fact": self._fact, "matched_locations": matched_locations, "where": self._where},
        )


def _location_text(session_snapshot: dict[str, Any], location: str) -> str:
    if location == "summary":
        project_metadata = session_snapshot.get("project_metadata") or {}
        derived = session_snapshot.get("last_derived_metadata") or {}
        return " ".join(
            [
                str(project_metadata.get("agreed_scope") or ""),
                str(derived.get("summary") or ""),
            ]
        )
    if location == "anchors":
        project_metadata = session_snapshot.get("project_metadata") or {}
        derived = session_snapshot.get("last_derived_metadata") or {}
        constraints = [
            *(project_metadata.get("explicit_constraints") or []),
            *(derived.get("detected_constraints") or []),
        ]
        return " ".join(str(item) for item in constraints)
    if location == "metadata":
        project_metadata = session_snapshot.get("project_metadata") or {}
        derived = session_snapshot.get("last_derived_metadata") or {}
        payload = {
            "project_name": project_metadata.get("project_name") or derived.get("project_name"),
            "mentioned_technologies": project_metadata.get("mentioned_technologies") or [],
            "detected_constraints": derived.get("detected_constraints") or [],
        }
        return json.dumps(payload, sort_keys=True)
    return ""
