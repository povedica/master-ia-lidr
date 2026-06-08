"""Tests for default deselection of slow/heavy pytest items."""

from __future__ import annotations

import pytest


@pytest.mark.slow
def test_slow_marker_fixture_for_collection_hook() -> None:
    """Collected only with --run-heavy or -m slow."""
    assert True


def test_fast_always_collected() -> None:
    assert True
