"""Few-shot estimation examples injected into the system prompt."""

from __future__ import annotations

import random
import re
from pathlib import Path

from pydantic import BaseModel, Field

from app.services.estimation_engine import EstimationMode


class EstimationExample(BaseModel):
    """One prior meeting summary paired with its reference estimate."""

    meeting_summary: str = Field(..., min_length=1)
    estimation: str = Field(..., min_length=1)


_EXAMPLES_ROOT = Path(__file__).resolve().parent / "examples"
_EXAMPLE_FILE_GLOB = "*.txt"
_FALLBACK_MODE = EstimationMode.STANDARD
def _normalize_example_text(raw_text: str) -> str:
    """Trim and normalize line endings; keep Markdown tables/headings intact for few-shot quality.

    Examples must preserve newlines so models imitate ``| Task | Hours | Cost (EUR) |`` blocks and
    ``Total hours`` / ``Total cost`` lines checked by ``evaluate_estimation_structure`` (same as
    ``ai-engineering/estimator``).
    """

    text = raw_text.replace("\r\n", "\n").replace("\r", "\n").strip()
    while "\n\n\n\n" in text:
        text = text.replace("\n\n\n\n", "\n\n\n")
    return text


def _load_example_pool(mode: EstimationMode) -> list[EstimationExample]:
    """Build the full pool of examples for one estimation mode from its directory."""

    mode_dir = _EXAMPLES_ROOT / mode.value
    if not mode_dir.is_dir():
        return []

    examples: list[EstimationExample] = []
    paths = sorted(p for p in mode_dir.glob(_EXAMPLE_FILE_GLOB) if p.is_file())
    for index, path in enumerate(paths, start=1):
        normalized = _normalize_example_text(path.read_text(encoding="utf-8"))
        if not normalized:
            continue
        examples.append(
            EstimationExample(
                meeting_summary=f"Historical {mode.value} estimation sample {index:02d}.",
                estimation=normalized,
            )
        )
    return examples


def load_examples(mode: EstimationMode) -> list[EstimationExample]:
    """Return a random subset (2–4) of file-based examples for the active mode.

    If the mode directory has no usable samples, falls back to ``standard`` so
    callers still get few-shot context until mode-specific corpora exist.
    """

    pool = _load_example_pool(mode)
    if not pool and mode is not _FALLBACK_MODE:
        pool = _load_example_pool(_FALLBACK_MODE)
    if len(pool) <= 2:
        return pool
    sample_size = random.randint(2, min(4, len(pool)))
    return random.sample(pool, k=sample_size)
