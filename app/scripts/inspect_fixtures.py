"""Inspect budget JSON fixtures in a directory."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from app.embedding_pipeline.loaders.filesystem import FileSystemLoader
from app.embedding_pipeline.parsers.budget_json import BudgetParseError, parse_budget_file


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Scan a directory and report valid/invalid budget JSON files.",
    )
    parser.add_argument("--dir", required=True, type=Path, help="Directory to inspect")
    args = parser.parse_args(argv)

    try:
        paths = list(FileSystemLoader.iter_budget_files(args.dir))
        valid = 0
        invalid = 0
        total_components = 0

        for path in paths:
            try:
                budget = parse_budget_file(path)
            except BudgetParseError:
                invalid += 1
                continue
            valid += 1
            total_components += len(budget.components)

        print(
            f"files={len(paths)} valid={valid} invalid={invalid} "
            f"total_components={total_components}"
        )
        return 0
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
