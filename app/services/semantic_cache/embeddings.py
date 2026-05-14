"""Embedding providers for semantic cache (interface + deterministic fake)."""

from __future__ import annotations

import hashlib
import math
import random
from typing import Protocol, runtime_checkable


@runtime_checkable
class EmbeddingProvider(Protocol):
    """Produces a dense vector for similarity search."""

    async def embed(self, text: str) -> list[float]: ...


class FakeEmbeddingProvider:
    """Deterministic pseudo-embedding for tests (normalized, stable under equal input)."""

    def __init__(self, dimensions: int = 32, seed: int = 42) -> None:
        if dimensions < 8:
            raise ValueError("dimensions must be at least 8")
        self._dimensions = dimensions
        self._seed = seed

    @property
    def dimensions(self) -> int:
        return self._dimensions

    async def embed(self, text: str) -> list[float]:
        digest = hashlib.sha256(text.encode("utf-8")).digest()
        seed_int = int.from_bytes(digest[:8], "big") ^ (self._seed & 0xFFFFFFFFFFFFFFFF)
        rng = random.Random(seed_int)
        vec = [rng.gauss(0.0, 1.0) for _ in range(self._dimensions)]
        norm = math.sqrt(sum(x * x for x in vec)) or 1.0
        return [x / norm for x in vec]
