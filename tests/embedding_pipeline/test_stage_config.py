"""Tests for StageConfig dataclass and mode A-D presets (feature-061 Step 1)."""

from __future__ import annotations

import dataclasses

import pytest

from app.embedding_pipeline.retrieval_service import RetrievalMode, resolve_mode
from app.embedding_pipeline.stage_config import (
    StageConfig,
    mode_a_preset,
    mode_b_preset,
    mode_c_preset,
    mode_d_preset,
)


def test_mode_a_preset_matches_retrieval_mode_a() -> None:
    config = mode_a_preset()
    plan = resolve_mode(RetrievalMode.A)

    assert config.search_mode == "vector"
    assert config.rerank is False
    assert config.routing_enabled is False
    assert config.query_transform is False
    assert config.temporal_decay is False
    assert plan.branches == ("vector",)
    assert plan.fusion_enabled is False
    assert plan.rerank_enabled is False


def test_mode_b_preset_matches_retrieval_mode_b() -> None:
    config = mode_b_preset()
    plan = resolve_mode(RetrievalMode.B)

    assert config.search_mode == "hybrid"
    assert config.rerank is False
    assert config.fusion == "rrf"
    assert plan.branches == ("vector", "lexical")
    assert plan.fusion_enabled is True
    assert plan.rerank_enabled is False


def test_mode_c_preset_matches_retrieval_mode_c() -> None:
    config = mode_c_preset()
    plan = resolve_mode(RetrievalMode.C)

    assert config.search_mode == "vector"
    assert config.rerank is True
    assert plan.branches == ("vector",)
    assert plan.fusion_enabled is False
    assert plan.rerank_enabled is True


def test_mode_d_preset_matches_retrieval_mode_d() -> None:
    config = mode_d_preset()
    plan = resolve_mode(RetrievalMode.D)

    assert config.search_mode == "hybrid"
    assert config.rerank is True
    assert config.fusion == "rrf"
    assert plan.branches == ("vector", "lexical")
    assert plan.fusion_enabled is True
    assert plan.rerank_enabled is True


def test_stage_config_is_frozen() -> None:
    config = mode_a_preset()
    with pytest.raises(dataclasses.FrozenInstanceError):
        config.rerank = True  # type: ignore[misc]


@pytest.mark.parametrize(
    ("search_mode", "fusion"),
    [
        ("invalid", "rrf"),
        ("vector", "invalid"),
    ],
)
def test_stage_config_rejects_invalid_literal_values(
    search_mode: str,
    fusion: str,
) -> None:
    with pytest.raises(ValueError):
        StageConfig(
            search_mode=search_mode,  # type: ignore[arg-type]
            rerank=False,
            query_transform=False,
            routing_enabled=False,
            fusion=fusion,  # type: ignore[arg-type]
            temporal_decay=False,
        )


def test_stage_config_accepts_round_robin_fusion() -> None:
    config = StageConfig(
        search_mode="hybrid",
        rerank=False,
        query_transform=False,
        routing_enabled=False,
        fusion="round_robin",
        temporal_decay=False,
    )
    assert config.fusion == "round_robin"
