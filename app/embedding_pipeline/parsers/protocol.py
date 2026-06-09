"""Parser protocol for upstream budget files."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from app.embedding_pipeline.schemas import Budget


class BudgetParser(Protocol):
    def __call__(self, path: Path) -> Budget: ...
