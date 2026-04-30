"""Few-shot estimation examples injected into the system prompt."""

from __future__ import annotations

import random
import re
from pathlib import Path

from pydantic import BaseModel, Field


class EstimationExample(BaseModel):
    """One prior meeting summary paired with its reference estimate."""

    meeting_summary: str = Field(..., min_length=1)
    estimation: str = Field(..., min_length=1)


_EXAMPLES_DIR = Path(__file__).resolve().parent / "examples"
_EXAMPLE_FILE_PATTERN = "sample-standard-*.txt"
_SPACE_PATTERN = re.compile(r"\s+")


def _normalize_example_text(raw_text: str) -> str:
    """Collapse newlines and repeated whitespace into single spaces."""

    return _SPACE_PATTERN.sub(" ", raw_text).strip()


def _load_example_pool() -> list[EstimationExample]:
    """Build the full pool of examples from sample files."""

    examples: list[EstimationExample] = []
    for index, path in enumerate(sorted(_EXAMPLES_DIR.glob(_EXAMPLE_FILE_PATTERN)), start=1):
        normalized = _normalize_example_text(path.read_text(encoding="utf-8"))
        if not normalized:
            continue
        examples.append(
            EstimationExample(
                meeting_summary=f"Historical estimation sample {index:02d}.",
                estimation=normalized,
            )
        )
    return examples


def load_examples() -> list[EstimationExample]:
    """Return a random subset (2-4) of file-based examples for prompting."""

    pool = _load_example_pool()
    if len(pool) <= 2:
        return pool
    sample_size = random.randint(2, min(4, len(pool)))
    return random.sample(pool, k=sample_size)
