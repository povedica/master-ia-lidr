"""Pytest fixtures for session estimation evals."""

from __future__ import annotations

import pytest

from tests.evals.loader import list_cases
from tests.evals.models import GoldenSessionCase


@pytest.fixture(scope="session")
def golden_cases() -> list[GoldenSessionCase]:
    return list_cases()


@pytest.fixture(scope="session")
def golden_case_ids(golden_cases: list[GoldenSessionCase]) -> list[str]:
    return [case.case_id for case in golden_cases]
