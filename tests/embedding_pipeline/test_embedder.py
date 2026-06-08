"""Unit tests for OpenAIEmbedder (feature-032)."""

from __future__ import annotations

import math
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from openai import RateLimitError

from app.config import Settings
from app.embedding_pipeline.embedder import (
    COST_PER_MILLION_TOKENS,
    DEFAULT_BATCH_SIZE,
    EMBEDDING_MODEL,
    OpenAIEmbedder,
)
from app.embedding_pipeline.schemas import Chunk, EmbeddedChunk
from tests.embedding_pipeline.conftest import SAMPLE_CHUNK

EMBEDDING_DIM = 1536
SAMPLE_TEXT = "OAuth 2.0 authentication backend for fintech"


def _make_vector(seed: float = 0.1) -> list[float]:
    return [seed + i * 0.0001 for i in range(EMBEDDING_DIM)]


def _embedding_response(vectors: list[list[float]]) -> MagicMock:
    data = [MagicMock(embedding=vec) for vec in vectors]
    return MagicMock(data=data)


def _chunk(
    chunk_id: str = "BUD-2024-014::AUTH-001",
    text: str = SAMPLE_TEXT,
    token_count: int = 42,
) -> Chunk:
    return Chunk.model_validate(
        {
            **SAMPLE_CHUNK,
            "chunk_id": chunk_id,
            "text": text,
            "token_count": token_count,
        }
    )


@pytest.fixture
def settings() -> Settings:
    return Settings(_env_file=None, openai_api_key="sk-test")


@pytest.fixture
def embedder(settings: Settings) -> OpenAIEmbedder:
    return OpenAIEmbedder(settings)


def test_module_constants() -> None:
    assert EMBEDDING_MODEL == "text-embedding-3-small"
    assert COST_PER_MILLION_TOKENS == 0.02
    assert DEFAULT_BATCH_SIZE == 100


@pytest.mark.asyncio
async def test_embed_one_returns_1536_finite_floats(
    embedder: OpenAIEmbedder,
) -> None:
    mock_create = AsyncMock(return_value=_embedding_response([_make_vector()]))
    with patch(
        "app.embedding_pipeline.embedder.AsyncOpenAI",
        return_value=MagicMock(embeddings=MagicMock(create=mock_create)),
    ):
        result = await embedder.embed_one(SAMPLE_TEXT)

    assert len(result) == EMBEDDING_DIM
    assert all(math.isfinite(x) for x in result)


@pytest.mark.asyncio
async def test_embed_many_batches_api_calls(embedder: OpenAIEmbedder) -> None:
    chunks = [_chunk(chunk_id=f"chunk-{i}", token_count=10) for i in range(250)]
    mock_create = AsyncMock(
        side_effect=[
            _embedding_response([_make_vector(0.1 + i) for i in range(100)]),
            _embedding_response([_make_vector(0.2 + i) for i in range(100)]),
            _embedding_response([_make_vector(0.3 + i) for i in range(50)]),
        ]
    )
    with patch(
        "app.embedding_pipeline.embedder.AsyncOpenAI",
        return_value=MagicMock(embeddings=MagicMock(create=mock_create)),
    ):
        await embedder.embed_many(chunks)

    assert mock_create.await_count == 3


@pytest.mark.asyncio
async def test_embed_many_preserves_order_and_fields(embedder: OpenAIEmbedder) -> None:
    chunks = [
        _chunk(chunk_id="first", text="alpha", token_count=5),
        _chunk(chunk_id="second", text="beta", token_count=7),
    ]
    mock_create = AsyncMock(
        return_value=_embedding_response([_make_vector(0.1), _make_vector(0.2)])
    )
    with patch(
        "app.embedding_pipeline.embedder.AsyncOpenAI",
        return_value=MagicMock(embeddings=MagicMock(create=mock_create)),
    ):
        result = await embedder.embed_many(chunks)

    assert len(result) == 2
    assert result[0].chunk_id == "first"
    assert result[0].text == "alpha"
    assert result[0].token_count == 5
    assert result[0].metadata == SAMPLE_CHUNK["metadata"]
    assert len(result[0].embedding) == EMBEDDING_DIM
    assert result[1].chunk_id == "second"
    assert isinstance(result[0], EmbeddedChunk)


@pytest.mark.asyncio
async def test_embed_many_empty_input(embedder: OpenAIEmbedder) -> None:
    mock_create = AsyncMock()
    with patch(
        "app.embedding_pipeline.embedder.AsyncOpenAI",
        return_value=MagicMock(embeddings=MagicMock(create=mock_create)),
    ):
        result = await embedder.embed_many([])

    assert result == []
    assert embedder.last_total_tokens == 0
    assert embedder.last_cost_usd == 0.0
    mock_create.assert_not_called()


@pytest.mark.asyncio
async def test_embed_many_tracks_tokens_and_cost(embedder: OpenAIEmbedder) -> None:
    chunks = [
        _chunk(chunk_id="a", token_count=100),
        _chunk(chunk_id="b", token_count=50),
    ]
    mock_create = AsyncMock(
        return_value=_embedding_response([_make_vector(), _make_vector(0.2)])
    )
    with patch(
        "app.embedding_pipeline.embedder.AsyncOpenAI",
        return_value=MagicMock(embeddings=MagicMock(create=mock_create)),
    ):
        await embedder.embed_many(chunks)

    assert embedder.last_total_tokens == 150
    expected_cost = 150 / 1_000_000 * COST_PER_MILLION_TOKENS
    assert embedder.last_cost_usd == pytest.approx(expected_cost)


@pytest.mark.asyncio
async def test_rate_limit_retries_with_backoff(embedder: OpenAIEmbedder) -> None:
    rate_error = RateLimitError("rate limited", response=MagicMock(), body=None)
    mock_create = AsyncMock(
        side_effect=[rate_error, rate_error, _embedding_response([_make_vector()])]
    )
    mock_sleep = AsyncMock()
    with (
        patch(
            "app.embedding_pipeline.embedder.AsyncOpenAI",
            return_value=MagicMock(embeddings=MagicMock(create=mock_create)),
        ),
        patch("app.embedding_pipeline.embedder.asyncio.sleep", mock_sleep),
    ):
        result = await embedder.embed_one(SAMPLE_TEXT)

    assert len(result) == EMBEDDING_DIM
    assert mock_create.await_count == 3
    mock_sleep.assert_any_await(1)
    mock_sleep.assert_any_await(2)


@pytest.mark.asyncio
async def test_rate_limit_reraises_after_max_retries(embedder: OpenAIEmbedder) -> None:
    rate_error = RateLimitError("rate limited", response=MagicMock(), body=None)
    mock_create = AsyncMock(side_effect=rate_error)
    with (
        patch(
            "app.embedding_pipeline.embedder.AsyncOpenAI",
            return_value=MagicMock(embeddings=MagicMock(create=mock_create)),
        ),
        patch("app.embedding_pipeline.embedder.asyncio.sleep", AsyncMock()),
        pytest.raises(RateLimitError),
    ):
        await embedder.embed_one(SAMPLE_TEXT)

    assert mock_create.await_count == 3


@pytest.mark.asyncio
async def test_non_rate_limit_error_propagates_without_retry(
    embedder: OpenAIEmbedder,
) -> None:
    mock_create = AsyncMock(side_effect=RuntimeError("boom"))
    with (
        patch(
            "app.embedding_pipeline.embedder.AsyncOpenAI",
            return_value=MagicMock(embeddings=MagicMock(create=mock_create)),
        ),
        patch("app.embedding_pipeline.embedder.asyncio.sleep", AsyncMock()) as mock_sleep,
        pytest.raises(RuntimeError, match="boom"),
    ):
        await embedder.embed_one(SAMPLE_TEXT)

    assert mock_create.await_count == 1
    mock_sleep.assert_not_called()


@pytest.mark.asyncio
async def test_embed_many_logs_per_batch(
    embedder: OpenAIEmbedder,
    caplog: pytest.LogCaptureFixture,
) -> None:
    chunks = [_chunk(chunk_id=f"c-{i}", token_count=3) for i in range(2)]
    mock_create = AsyncMock(
        return_value=_embedding_response([_make_vector(0.1), _make_vector(0.2)])
    )
    with (
        patch(
            "app.embedding_pipeline.embedder.AsyncOpenAI",
            return_value=MagicMock(embeddings=MagicMock(create=mock_create)),
        ),
        caplog.at_level("INFO"),
    ):
        await embedder.embed_many(chunks)

    batch_logs = [r for r in caplog.records if r.message == "embedding_batch_completed"]
    assert len(batch_logs) == 1
    record = batch_logs[0]
    assert record.batch_index == 0
    assert record.batch_size == 2
    assert record.batch_tokens == 6
    assert isinstance(record.latency_ms, (int, float))
    assert record.latency_ms >= 0


@pytest.mark.asyncio
async def test_wrong_embedding_dimension_raises(embedder: OpenAIEmbedder) -> None:
    mock_create = AsyncMock(return_value=_embedding_response([[0.1, 0.2, 0.3]]))
    with (
        patch(
            "app.embedding_pipeline.embedder.AsyncOpenAI",
            return_value=MagicMock(embeddings=MagicMock(create=mock_create)),
        ),
        pytest.raises(ValueError, match="1536"),
    ):
        await embedder.embed_one(SAMPLE_TEXT)


@pytest.mark.asyncio
async def test_missing_api_key_raises_at_call_time() -> None:
    embedder = OpenAIEmbedder(Settings(_env_file=None, openai_api_key=""))
    with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
        await embedder.embed_one(SAMPLE_TEXT)
