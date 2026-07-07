"""Stage configuration for advanced retrieval pipeline (feature-061)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

SearchMode = Literal["vector", "hybrid"]
FusionMethod = Literal["rrf", "round_robin"]

_VALID_SEARCH_MODES = frozenset({"vector", "hybrid"})
_VALID_FUSION_METHODS = frozenset({"rrf", "round_robin"})


@dataclass(frozen=True)
class StageConfig:
    """Controls query transform, routing, fusion, rerank, and temporal decay."""

    search_mode: SearchMode
    rerank: bool
    query_transform: bool
    routing_enabled: bool
    fusion: FusionMethod
    temporal_decay: bool

    def __post_init__(self) -> None:
        if self.search_mode not in _VALID_SEARCH_MODES:
            raise ValueError(f"Unsupported search_mode: {self.search_mode}")
        if self.fusion not in _VALID_FUSION_METHODS:
            raise ValueError(f"Unsupported fusion method: {self.fusion}")


def mode_a_preset() -> StageConfig:
    """Vector-only retrieval without rerank (RetrievalMode.A)."""
    return StageConfig(
        search_mode="vector",
        rerank=False,
        query_transform=False,
        routing_enabled=False,
        fusion="rrf",
        temporal_decay=False,
    )


def mode_b_preset() -> StageConfig:
    """Hybrid RRF retrieval without rerank (RetrievalMode.B)."""
    return StageConfig(
        search_mode="hybrid",
        rerank=False,
        query_transform=False,
        routing_enabled=False,
        fusion="rrf",
        temporal_decay=False,
    )


def mode_c_preset() -> StageConfig:
    """Vector-only retrieval with rerank (RetrievalMode.C)."""
    return StageConfig(
        search_mode="vector",
        rerank=True,
        query_transform=False,
        routing_enabled=False,
        fusion="rrf",
        temporal_decay=False,
    )


def mode_d_preset() -> StageConfig:
    """Hybrid RRF retrieval with rerank (RetrievalMode.D)."""
    return StageConfig(
        search_mode="hybrid",
        rerank=True,
        query_transform=False,
        routing_enabled=False,
        fusion="rrf",
        temporal_decay=False,
    )
