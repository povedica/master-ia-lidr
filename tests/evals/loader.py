"""Load and validate golden session YAML fixtures."""

from __future__ import annotations

from pathlib import Path

import yaml

from tests.evals.models import GoldenSessionCase

_GOLDEN_DIR = Path(__file__).resolve().parent / "fixtures" / "golden_sessions"


class GoldenLoaderError(ValueError):
    """Raised when a golden fixture fails validation."""


def golden_sessions_dir() -> Path:
    return _GOLDEN_DIR


def list_case_files() -> list[Path]:
    if not _GOLDEN_DIR.is_dir():
        return []
    return sorted(_GOLDEN_DIR.glob("*.yaml"))


def load_case_file(path: Path) -> GoldenSessionCase:
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise GoldenLoaderError(f"invalid YAML in {path.name}: {exc}") from exc
    if not isinstance(raw, dict):
        raise GoldenLoaderError(f"{path.name}: root must be a mapping")
    try:
        return GoldenSessionCase.model_validate(raw)
    except Exception as exc:
        raise GoldenLoaderError(f"{path.name}: {exc}") from exc


def list_cases() -> list[GoldenSessionCase]:
    cases: list[GoldenSessionCase] = []
    for path in list_case_files():
        cases.append(load_case_file(path))
    return cases


def get_case(case_id: str) -> GoldenSessionCase:
    for case in list_cases():
        if case.case_id == case_id:
            return case
    raise GoldenLoaderError(f"unknown case_id: {case_id!r}")
