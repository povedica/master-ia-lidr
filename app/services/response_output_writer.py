"""Persist successful estimation outputs as markdown files."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

# Repository root: .../<repo>/app/services/<this file> → parents[2] == <repo>
_REPO_ROOT = Path(__file__).resolve().parents[2]
_OUTPUT_DIR = _REPO_ROOT / "output-responses"


class ResponseOutputPersistError(RuntimeError):
    """Raised when estimation output cannot be persisted safely."""


def build_output_filename(now: datetime | None = None) -> str:
    """Return timestamp-based output filename in UTC."""
    reference = now or datetime.now(UTC)
    return f"response-{reference.strftime('%Y%m%d-%H%M%S')}.md"


def persist_estimation_output(estimation: str) -> Path:
    """Write estimation markdown to output-responses and return destination path."""
    filename = build_output_filename()
    destination = _OUTPUT_DIR / filename
    try:
        _OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        destination.write_text(estimation, encoding="utf-8")
    except OSError as exc:
        raise ResponseOutputPersistError("failed to persist estimation output") from exc
    return destination
