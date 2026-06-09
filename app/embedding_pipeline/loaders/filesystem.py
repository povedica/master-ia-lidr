"""Filesystem loader for budget JSON files."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path


class FileSystemLoader:
    """Yield budget JSON files from a single directory (non-recursive)."""

    @staticmethod
    def iter_budget_files(directory: Path) -> Iterator[Path]:
        if not directory.is_dir():
            raise FileNotFoundError(f"Budget directory not found: {directory}")
        for path in sorted(directory.iterdir()):
            if path.is_file() and path.suffix == ".json":
                yield path
