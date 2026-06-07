"""Persist LLM request/response pairs as JSON for local debugging."""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, is_dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.config import get_settings
from app.services.llm_call_audit import snapshot_llm_call_preparation

logger = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parents[2]
_OUTPUT_DIR = _REPO_ROOT / "output-responses"
_sequence = 0


class LlmCallPersistError(RuntimeError):
    """Raised when an LLM call record cannot be written safely."""


def build_llm_call_filename(now: datetime | None = None, *, sequence: int = 0) -> str:
    """Return timestamp-based JSON filename in UTC."""

    reference = now or datetime.now(UTC)
    return f"llm-call-{reference.strftime('%Y%m%d-%H%M%S')}-{sequence:03d}.json"


def _next_sequence() -> int:
    global _sequence
    _sequence += 1
    return _sequence


def sanitize_request_kwargs(kwargs: dict[str, Any]) -> dict[str, Any]:
    """Drop secret-bearing keys from kwargs before persistence."""

    return {key: value for key, value in kwargs.items() if key != "api_key"}


def usage_to_dict(usage: Any | None) -> dict[str, Any] | None:
    """Serialize UsageInfo (or compatible dataclass) for JSON output."""

    if usage is None:
        return None
    if is_dataclass(usage) and not isinstance(usage, type):
        return asdict(usage)
    return dict(usage)


def persist_llm_call_record(record: dict[str, Any]) -> Path:
    """Write one LLM call record as pretty JSON and return destination path."""

    filename = build_llm_call_filename(sequence=_next_sequence())
    destination = _OUTPUT_DIR / filename
    try:
        _OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        destination.write_text(
            json.dumps(record, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except OSError as exc:
        raise LlmCallPersistError("failed to persist LLM call record") from exc
    return destination


def build_llm_call_record(
    *,
    call_kind: str,
    model_request: dict[str, Any],
    response: dict[str, Any],
    preparation: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the persisted JSON document with preparation separated from model_request."""

    return {
        "recorded_at_utc": datetime.now(UTC).isoformat(),
        "call_kind": call_kind,
        "preparation": preparation if preparation is not None else snapshot_llm_call_preparation(),
        "model_request": model_request,
        "response": response,
    }


def maybe_persist_llm_call(record: dict[str, Any]) -> Path | None:
    """Best-effort persist when the feature toggle is enabled."""

    if not get_settings().llm_call_persist_enabled:
        return None
    try:
        return persist_llm_call_record(record)
    except LlmCallPersistError:
        logger.warning(
            "llm_call_persist_failed",
            extra={"call_kind": record.get("call_kind"), "error_type": "filesystem"},
        )
        return None
