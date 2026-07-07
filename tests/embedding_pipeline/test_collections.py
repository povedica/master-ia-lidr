"""Unit tests for multi-index collection registry (feature-063)."""

from __future__ import annotations

import pytest

from app.embedding_pipeline.collections import Collection, match_collections
from app.embedding_pipeline.retrieval_router import route_collection


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("meeting transcript from client kick-off", Collection.TRANSCRIPTS),
        ("budget estimate hours for CRM", Collection.BUDGETS),
        ("architecture specification runbook", Collection.TECHNICAL_DOCS),
    ],
)
def test_match_collections_detects_vocabulary(query: str, expected: Collection) -> None:
    matches = match_collections(query)
    assert expected in matches


def test_route_collection_uses_rules_when_enabled() -> None:
    routed = route_collection(
        "client meeting transcript discussion",
        config_enabled=True,
        settings_enabled=True,
    )
    assert routed == Collection.TRANSCRIPTS.value


def test_route_collection_defaults_to_budgets_when_disabled() -> None:
    routed = route_collection(
        "meeting transcript",
        config_enabled=False,
        settings_enabled=True,
    )
    assert routed == Collection.BUDGETS.value
