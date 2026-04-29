"""Load mode-specific system prompt fragments from plain text files."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from app.services.estimation_engine import EstimationMode

_PROMPTS_DIR = Path(__file__).resolve().parent


@lru_cache
def load_mode_prompt(mode: EstimationMode) -> str:
    """Return UTF-8 prompt body for the given adaptive mode (no secrets)."""

    path = _PROMPTS_DIR / f"{mode.value}.txt"
    return path.read_text(encoding="utf-8").strip()
