"""JSON budget file parser."""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import ValidationError

from app.embedding_pipeline.schemas import Budget


class BudgetParseError(ValueError):
    """Raised when a budget file cannot be parsed or validated."""


def parse_budget_file(path: Path) -> Budget:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise BudgetParseError(f"Invalid JSON in budget file: {path}") from exc

    try:
        return Budget.model_validate(payload)
    except ValidationError as exc:
        raise BudgetParseError(f"Invalid budget schema in file: {path}") from exc
