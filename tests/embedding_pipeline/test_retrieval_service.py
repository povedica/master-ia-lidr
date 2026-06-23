"""Tests for production retrieval service (feature-050)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.config import Settings
from app.embedding_pipeline.lexical_search_repository import LexicalSearchResult
from app.embedding_pipeline.rerank import CrossEncoderReranker, NoOpReranker
from app.embedding_pipeline.retrieval_service import (
    RetrievalMode,
    RetrievalService,
    parse_retrieval_mode,
    resolve_mode,
)
from app.embedding_pipeline.schemas import SearchResult


def test_resolve_mode_maps_abcd_to_branch_plan() -> None:
    plan_a = resolve_mode(RetrievalMode.A)
    plan_b = resolve_mode(RetrievalMode.B)
    plan_c = resolve_mode(RetrievalMode.C)
    plan_d = resolve_mode(RetrievalMode.D)

    assert plan_a.branches == ("vector",)
    assert plan_a.fusion_enabled is False
    assert plan_a.rerank_enabled is False

    assert plan_b.branches == ("vector", "lexical")
    assert plan_b.fusion_enabled is True
    assert plan_b.rerank_enabled is False

    assert plan_c.branches == ("vector",)
    assert plan_c.fusion_enabled is False
    assert plan_c.rerank_enabled is True

    assert plan_d.branches == ("vector", "lexical")
    assert plan_d.fusion_enabled is True
    assert plan_d.rerank_enabled is True


def test_parse_retrieval_mode_is_case_insensitive() -> None:
    assert parse_retrieval_mode("b") == RetrievalMode.B


class _FakeEmbedder:
    async def embed_one(self, text: str) -> list[float]:
        del text
        return [0.1, 0.2, 0.3]


class _FakeVectorRepository:
    async def search_chunks(self, session, *, query_vector, k):
        del session, query_vector, k
        return [
            SearchResult(
                chunk_id=101,
                document_id=1,
                chunk_type="budget_component",
                content="OAuth2 backend",
                distance=0.2,
                metadata={"budget_id": "BUD-2024-014"},
            ),
            SearchResult(
                chunk_id=102,
                document_id=2,
                chunk_type="budget_component",
                content="Payments app",
                distance=0.4,
                metadata={"budget_id": "BUD-2024-099"},
            ),
        ]


class _FakeLexicalRepository:
    async def search_chunks(self, session, *, query, top_k):
        del session, query
        return [
            LexicalSearchResult(
                chunk_id=201,
                document_id=3,
                chunk_type="budget_component",
                content="Stripe integration OAuth2",
                metadata={"budget_id": "BUD-2024-032"},
                ts_rank=0.9,
                matched_terms=["oauth2", "stripe"],
            ),
            LexicalSearchResult(
                chunk_id=101,
                document_id=1,
                chunk_type="budget_component",
                content="OAuth2 backend",
                metadata={"budget_id": "BUD-2024-014"},
                ts_rank=0.5,
                matched_terms=["oauth2"],
            ),
        ][:top_k]


@pytest.mark.asyncio
async def test_retrieve_mode_a_returns_vector_only_order() -> None:
    service = RetrievalService()
    settings = Settings(_env_file=None)

    response = await service.retrieve(
        "OAuth2 backend",
        mode=RetrievalMode.A,
        recall_k=10,
        top_k_final=2,
        session=AsyncMock(),
        embedder=_FakeEmbedder(),
        reranker=NoOpReranker(),
        settings=settings,
        vector_repository=_FakeVectorRepository(),
        lexical_repository=_FakeLexicalRepository(),
    )

    assert response.mode == "A"
    assert [row.chunk_id for row in response.results] == [101, 102]
    assert response.results[0].vector_score is not None
    assert response.results[0].lexical_score is None
    assert response.results[0].fusion_score is None
    assert response.results[0].rerank_score is None


@pytest.mark.asyncio
async def test_retrieve_mode_b_fuses_vector_and_lexical() -> None:
    service = RetrievalService()
    settings = Settings(_env_file=None)

    response = await service.retrieve(
        "OAuth2 Stripe",
        mode=RetrievalMode.B,
        recall_k=10,
        top_k_final=3,
        session=AsyncMock(),
        embedder=_FakeEmbedder(),
        reranker=NoOpReranker(),
        settings=settings,
        vector_repository=_FakeVectorRepository(),
        lexical_repository=_FakeLexicalRepository(),
    )

    assert response.mode == "B"
    assert response.applied_config.fusion is not None
    assert response.applied_config.fusion.method == "rrf"
    assert any(row.fusion_score is not None for row in response.results)
    assert any(row.matched_terms for row in response.results)


@pytest.mark.asyncio
async def test_retrieve_mode_c_degrades_when_reranker_is_noop() -> None:
    service = RetrievalService()
    settings = Settings(_env_file=None, retrieval_rerank_enabled=True)

    response = await service.retrieve(
        "OAuth2 backend",
        mode=RetrievalMode.C,
        recall_k=10,
        top_k_final=2,
        session=AsyncMock(),
        embedder=_FakeEmbedder(),
        reranker=NoOpReranker(),
        settings=settings,
        vector_repository=_FakeVectorRepository(),
        lexical_repository=_FakeLexicalRepository(),
    )

    assert response.mode == "A"
    assert any("no-op" in warning.lower() for warning in response.warnings)


@pytest.mark.asyncio
async def test_retrieve_mode_c_reranks_with_cross_encoder_fake_scorer() -> None:
    service = RetrievalService()
    settings = Settings(
        _env_file=None,
        retrieval_rerank_enabled=True,
        retrieval_rerank_model="fake-model",
    )

    def predict(pairs):
        del pairs
        return [0.2, 0.9]

    reranker = CrossEncoderReranker("fake-model", predict=predict)

    response = await service.retrieve(
        "OAuth2 backend",
        mode=RetrievalMode.C,
        recall_k=10,
        top_k_final=2,
        session=AsyncMock(),
        embedder=_FakeEmbedder(),
        reranker=reranker,
        settings=settings,
        vector_repository=_FakeVectorRepository(),
        lexical_repository=_FakeLexicalRepository(),
    )

    assert response.mode == "C"
    assert [row.chunk_id for row in response.results] == [102, 101]
    assert response.results[0].rerank_score == pytest.approx(1.0)


@pytest.mark.asyncio
async def test_retrieve_mode_d_hybrid_then_rerank() -> None:
    service = RetrievalService()
    settings = Settings(
        _env_file=None,
        retrieval_rerank_enabled=True,
        retrieval_rerank_model="fake-model",
    )

    chunk_scores = {
        101: 0.4,
        102: 0.3,
        201: 0.95,
    }

    def predict(pairs):
        return [chunk_scores[int(content.split()[0].replace("chunk", ""))] if False else 0.1 for _, content in pairs]

    def predict_by_content(pairs):
        scores = []
        for _, content in pairs:
            if "Stripe" in content:
                scores.append(0.95)
            elif "Payments" in content:
                scores.append(0.2)
            else:
                scores.append(0.5)
        return scores

    reranker = CrossEncoderReranker("fake-model", predict=predict_by_content)

    response = await service.retrieve(
        "OAuth2 Stripe",
        mode=RetrievalMode.D,
        recall_k=10,
        top_k_final=2,
        session=AsyncMock(),
        embedder=_FakeEmbedder(),
        reranker=reranker,
        settings=settings,
        vector_repository=_FakeVectorRepository(),
        lexical_repository=_FakeLexicalRepository(),
    )

    assert response.mode == "D"
    assert response.results[0].chunk_id == 201
    assert "rerank" in response.results[0].source_strategies


@pytest.mark.asyncio
async def test_retrieve_vector_branch_failure_returns_partial_result_with_warning() -> None:
    class _FailingVectorRepository:
        async def search_chunks(self, session, *, query_vector, k):
            del session, query_vector, k
            raise RuntimeError("vector down")

    service = RetrievalService()
    settings = Settings(_env_file=None)

    response = await service.retrieve(
        "OAuth2 Stripe",
        mode=RetrievalMode.B,
        recall_k=10,
        top_k_final=2,
        session=AsyncMock(),
        embedder=_FakeEmbedder(),
        reranker=NoOpReranker(),
        settings=settings,
        vector_repository=_FailingVectorRepository(),
        lexical_repository=_FakeLexicalRepository(),
    )

    assert any("Vector branch failed" in warning for warning in response.warnings)
    assert response.results
