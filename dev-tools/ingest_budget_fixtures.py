#!/usr/bin/env python3
"""Ingest all valid budget JSON fixtures via POST /api/v1/embeddings/ingest.

Uses ``httpx`` (dev dependency). Reads budgets from
``tests/embedding_pipeline/fixtures/budget_files/*.json`` (non-recursive; skips
subfolders such as ``invalids/``).

Examples (from the repository root)::

    docker compose up -d postgres
    export DATABASE_URL=postgresql+asyncpg://estimator:estimator@127.0.0.1:5432/estimator
    uv run alembic upgrade head
    uv run uvicorn app.main:app --reload

    uv run python dev-tools/ingest_budget_fixtures.py
    uv run python dev-tools/ingest_budget_fixtures.py --dry-run
    uv run python dev-tools/ingest_budget_fixtures.py --base-url http://localhost:8000
    uv run python dev-tools/ingest_budget_fixtures.py --skip-existing

Warning: budgets with components trigger real OpenAI embedding calls unless the API
uses mocks. Zero-component fixtures skip the embedder.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import httpx

_DEFAULT_BASE_URL = "http://127.0.0.1:8000"
_DEFAULT_BUDGETS_DIR = (
    Path(__file__).resolve().parent.parent
    / "tests"
    / "embedding_pipeline"
    / "fixtures"
    / "budget_files"
)
_INGEST_PATH = "/api/v1/embeddings/ingest"
_SOURCE_PATH_PREFIX = "data/budgets"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="POST each budget fixture to /api/v1/embeddings/ingest.",
    )
    parser.add_argument(
        "--base-url",
        default=_DEFAULT_BASE_URL,
        help=f"API base URL (default: {_DEFAULT_BASE_URL}).",
    )
    parser.add_argument(
        "--budgets-dir",
        type=Path,
        default=_DEFAULT_BUDGETS_DIR,
        help=f"Directory with budget *.json files (default: {_DEFAULT_BUDGETS_DIR}).",
    )
    parser.add_argument(
        "--document-type",
        default="historical_budget",
        help='Value for request "document_type" (default: historical_budget).',
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print payloads only; do not call the API.",
    )
    parser.add_argument(
        "--skip-existing",
        action="store_true",
        help="Treat HTTP 409 (duplicate source_path) as success.",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=120.0,
        help="Per-request timeout in seconds (default: 120).",
    )
    return parser.parse_args()


def _iter_budget_files(directory: Path) -> list[Path]:
    if not directory.is_dir():
        raise FileNotFoundError(f"Budget directory not found: {directory}")
    return sorted(
        path for path in directory.iterdir() if path.is_file() and path.suffix == ".json"
    )


def _document_metadata(budget: dict[str, Any], *, fixture_name: str) -> dict[str, object]:
    client = budget.get("client_metadata") or {}
    return {
        "budget_id": budget.get("budget_id", ""),
        "client_sector": client.get("sector", ""),
        "main_technology": budget.get("main_technology", ""),
        "year": budget.get("year", 0),
        "fixture_file": fixture_name,
        "ingest_tool": "dev-tools/ingest_budget_fixtures.py",
    }


def _build_payload(
    budget_path: Path,
    *,
    document_type: str,
) -> dict[str, object]:
    budget = json.loads(budget_path.read_text(encoding="utf-8"))
    source_path = f"{_SOURCE_PATH_PREFIX}/{budget_path.name}"
    return {
        "source_path": source_path,
        "document_type": document_type,
        "metadata": _document_metadata(budget, fixture_name=budget_path.name),
        "content": budget,
    }


def _print_result(
    *,
    budget_path: Path,
    status_code: int,
    body: dict[str, object] | list[object] | str,
) -> None:
    if status_code == 200 and isinstance(body, dict):
        print(
            f"OK  {budget_path.name}: document_id={body.get('document_id')} "
            f"chunks_created={body.get('chunks_created')} "
            f"ms={body.get('ingestion_time_ms')}"
        )
        return
    if status_code == 409 and isinstance(body, dict):
        print(
            f"SKIP {budget_path.name}: duplicate document_id={body.get('document_id')}"
        )
        return
    print(f"FAIL {budget_path.name}: HTTP {status_code} {body}", file=sys.stderr)


def main() -> int:
    args = _parse_args()
    budget_files = _iter_budget_files(args.budgets_dir)
    if not budget_files:
        print(f"No budget JSON files in {args.budgets_dir}", file=sys.stderr)
        return 1

    print(f"Found {len(budget_files)} budget file(s) in {args.budgets_dir}")

    failures = 0
    skipped = 0
    succeeded = 0

    if args.dry_run:
        for budget_path in budget_files:
            payload = _build_payload(
                budget_path,
                document_type=args.document_type,
            )
            print(json.dumps({"file": budget_path.name, "payload": payload}, indent=2))
        return 0

    ingest_url = f"{args.base_url.rstrip('/')}{_INGEST_PATH}"
    with httpx.Client(timeout=args.timeout) as client:
        for budget_path in budget_files:
            payload = _build_payload(
                budget_path,
                document_type=args.document_type,
            )
            try:
                response = client.post(ingest_url, json=payload)
            except httpx.HTTPError as exc:
                print(f"FAIL {budget_path.name}: {exc}", file=sys.stderr)
                failures += 1
                continue

            try:
                body: dict[str, object] | list[object] | str = response.json()
            except json.JSONDecodeError:
                body = response.text

            _print_result(
                budget_path=budget_path,
                status_code=response.status_code,
                body=body,
            )

            if response.status_code == 200:
                succeeded += 1
            elif response.status_code == 409 and args.skip_existing:
                skipped += 1
            elif response.status_code == 409:
                failures += 1
            else:
                failures += 1

    print(
        f"Done: {succeeded} ingested, {skipped} skipped (409), {failures} failed "
        f"of {len(budget_files)} total."
    )
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
