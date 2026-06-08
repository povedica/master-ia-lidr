"""Unit tests for compare CLI cosine similarity (feature-034)."""

from __future__ import annotations

import math
from io import StringIO
from unittest.mock import AsyncMock, patch

import pytest

from app.scripts.compare import cosine_similarity, main


def test_cosine_similarity_identical_vectors() -> None:
    vector = [1.0, 2.0, 3.0]
    assert cosine_similarity(vector, vector) == pytest.approx(1.0)


def test_cosine_similarity_orthogonal_vectors() -> None:
    assert cosine_similarity([1.0, 0.0], [0.0, 1.0]) == pytest.approx(0.0)


def test_cosine_similarity_opposite_vectors() -> None:
    assert cosine_similarity([1.0, 0.0], [-1.0, 0.0]) == pytest.approx(-1.0)


def test_cosine_similarity_zero_norm_returns_zero() -> None:
    assert cosine_similarity([0.0, 0.0], [1.0, 2.0]) == 0.0
    assert cosine_similarity([1.0, 2.0], [0.0, 0.0]) == 0.0


def test_main_prints_texts_and_similarity(capsys: pytest.CaptureFixture[str]) -> None:
    vector_a = [1.0, 0.0, 0.0]
    vector_b = [0.0, 1.0, 0.0]

    with patch(
        "app.scripts.compare.OpenAIEmbedder",
    ) as mock_embedder_cls:
        instance = mock_embedder_cls.return_value
        instance.embed_one = AsyncMock(side_effect=[vector_a, vector_b])

        exit_code = main(
            ["--text-a", "OAuth backend", "--text-b", "Database migration"]
        )

    assert exit_code == 0
    captured = capsys.readouterr()
    assert "OAuth backend" in captured.out
    assert "Database migration" in captured.out
    assert "Cosine similarity:" in captured.out
    assert "0.0000" in captured.out


def test_main_missing_text_a_exits_nonzero(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc_info:
        main(["--text-b", "only b"])
    assert exc_info.value.code != 0
    assert capsys.readouterr().err
