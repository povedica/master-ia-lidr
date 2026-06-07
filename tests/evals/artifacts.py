"""Optional JSON artifacts for failed judge eval runs."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_ARTIFACTS_DIR = Path(__file__).resolve().parent / "artifacts"


def artifacts_dir() -> Path:
    _ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    return _ARTIFACTS_DIR


def write_judge_failure_artifact(
    *,
    case_id: str,
    scores: dict[str, float | None],
    context_block: str,
    extra: dict[str, Any] | None = None,
) -> Path:
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    path = artifacts_dir() / f"judge-failure-{case_id}-{timestamp}.json"
    payload = {
        "case_id": case_id,
        "timestamp": timestamp,
        "scores": scores,
        "context_block": context_block,
        "extra": extra or {},
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path
