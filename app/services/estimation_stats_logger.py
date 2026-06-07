"""Append-only JSON Lines log for per-request estimation metadata (no estimation body)."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.services.llm_service import LlmEstimationCallOutcome

logger = logging.getLogger(__name__)

# Repository root: .../<repo>/app/services/<this file> → parents[2] == <repo>
_MASTER_IA_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_STATS_LOG_PATH = _MASTER_IA_ROOT / "output-stats" / "estimation-stats.jsonl"


class EstimationStatsLogError(OSError):
    """Raised when stats cannot be appended to the log file."""


def resolve_stats_log_path(configured: str) -> Path:
    """Return the log path; empty `configured` uses the default under output-stats/."""

    text = configured.strip()
    if not text:
        return _DEFAULT_STATS_LOG_PATH
    return Path(text).expanduser()


def build_estimation_stats_record(
    *,
    result: LlmEstimationCallOutcome,
    structure_score: float,
    request_id: str,
    timestamp: datetime,
    latency_ms: int,
    prompt_version: str,
    examples_version: str,
    estimated_cost_usd: float | None,
) -> dict[str, Any]:
    """Shape one log record: mirrors API metadata fields without the estimation text."""

    ts = timestamp if timestamp.tzinfo else timestamp.replace(tzinfo=UTC)
    stamp = ts.isoformat(timespec="microseconds").replace("+00:00", "Z")

    record: dict[str, Any] = {
        "model": result.model,
        "provider": result.provider,
        "request_id": request_id,
        "timestamp": stamp,
        "latency_ms": latency_ms,
        "prompt_version": prompt_version,
        "examples_version": examples_version,
        "degraded": result.degraded,
    }

    record["score"] = structure_score
    record["finish_reason"] = result.finish_reason

    if result.usage is not None:
        record["usage"] = {
            "prompt_tokens": result.usage.prompt_tokens,
            "completion_tokens": result.usage.completion_tokens,
            "total_tokens": result.usage.total_tokens,
            "preprocessing_input_tokens": result.usage.preprocessing_input_tokens,
            "preprocessing_output_tokens": result.usage.preprocessing_output_tokens,
            "estimated_cost_usd": estimated_cost_usd,
        }

    return record


def append_estimation_stats_line(path: Path, record: dict[str, Any]) -> None:
    """Append one JSON object as a single line (NDJSON)."""

    line = json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n"
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(line)
    except OSError as exc:
        raise EstimationStatsLogError("failed to append estimation stats") from exc


def try_append_estimation_stats(
    *,
    path: Path,
    result: LlmEstimationCallOutcome,
    structure_score: float,
    request_id: str,
    timestamp: datetime,
    latency_ms: int,
    prompt_version: str,
    examples_version: str,
    estimated_cost_usd: float | None,
) -> None:
    """Best-effort append; logs a warning on failure without raising."""

    record = build_estimation_stats_record(
        result=result,
        structure_score=structure_score,
        request_id=request_id,
        timestamp=timestamp,
        latency_ms=latency_ms,
        prompt_version=prompt_version,
        examples_version=examples_version,
        estimated_cost_usd=estimated_cost_usd,
    )
    try:
        append_estimation_stats_line(path, record)
    except EstimationStatsLogError:
        logger.warning(
            "estimation_stats_log_append_failed",
            extra={"path": str(path)},
            exc_info=True,
        )
