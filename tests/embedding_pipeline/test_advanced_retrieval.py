"""Tests for advanced_retrieve() core orchestration (feature-061 Step 2)."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from app.config import Settings
from app.embedding_pipeline.advanced_retrieval import advanced_retrieve, resolve_stage_plan
from app.embedding_pipeline.lexical_search_repository import LexicalSearchResult
from app.embedding_pipeline.rerank import CrossEncoderReranker, NoOpReranker
from app.embedding_pipeline.retrieval_service import RetrievalMode
from app.embedding_pipeline.schemas import SearchResult
from app.embedding_pipeline.stage_config import (
    mode_a_preset,
    mode_b_preset,
    mode_c_preset,
    mode_d_preset,
)


def test_resolve_stage_plan_maps_presets_to_branch_plan() -> None:
    plan_a = resolve_stage_plan(mode_a_preset())
    plan_b = resolve_stage_plan(mode_b_preset())
    plan_c = resolve_stage_plan(mode_c_preset())
    plan_d = resolve_stage_plan(mode_d_preset())

    assert plan_a.branches == ("vector",)
    assert plan_a.fusion_enabled is False
    assert plan_a.rerank_enabled is False

    assert plan_b.branches == ("vector", "lexical")
    assert plan_b.fusion_enabled is True
    assert plan_b.rerank_enabled is False

    assert plan_c.branches == ("vector",)
    assert plan_c.rerank_enabled is True

    assert plan_d.branches == ("vector", "lexical")
    assert plan_d.fusion_enabled is True
    assert plan_d.rerank_enabled is True


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
async def test_advanced_retrieve_mode_a_vector_only() -> None:
    settings = Settings(_env_file=None)

    response = await advanced_retrieve(
        AsyncMock(),
        "OAuth2 backend",
        mode_a_preset(),
        recall_k=10,
        top_k_final=2,
        embedder=_FakeEmbedder(),
        reranker=NoOpReranker(),
        settings=settings,
        vector_repository=_FakeVectorRepository(),
        lexical_repository=_FakeLexicalRepository(),
    )

    assert [row.chunk_id for row in response.results] == [101, 102]
    assert all(row.collection == "budgets" for row in response.results)
    assert response.results[0].vector_score is not None
    assert response.results[0].fusion_score is None
    assert response.results[0].rerank_score is None


@pytest.mark.asyncio
async def test_advanced_retrieve_mode_b_hybrid_rrf_fusion() -> None:
    settings = Settings(_env_file=None)

    response = await advanced_retrieve(
        AsyncMock(),
        "OAuth2 Stripe",
        mode_b_preset(),
        recall_k=10,
        top_k_final=3,
        embedder=_FakeEmbedder(),
        reranker=NoOpReranker(),
        settings=settings,
        vector_repository=_FakeVectorRepository(),
        lexical_repository=_FakeLexicalRepository(),
    )

    assert any(row.fusion_score is not None for row in response.results)
    assert any(row.matched_terms for row in response.results)
    assert all(row.collection == "budgets" for row in response.results)


@pytest.mark.asyncio
async def test_advanced_retrieve_mode_c_reranks_with_cross_encoder() -> None:
    settings = Settings(
        _env_file=None,
        retrieval_rerank_enabled=True,
        retrieval_rerank_model="fake-model",
    )

    def predict(pairs):
        del pairs
        return [0.2, 0.9]

    reranker = CrossEncoderReranker("fake-model", predict=predict)

    response = await advanced_retrieve(
        AsyncMock(),
        "OAuth2 backend",
        mode_c_preset(),
        recall_k=10,
        top_k_final=2,
        embedder=_FakeEmbedder(),
        reranker=reranker,
        settings=settings,
        vector_repository=_FakeVectorRepository(),
        lexical_repository=_FakeLexicalRepository(),
    )

    assert [row.chunk_id for row in response.results] == [102, 101]
    assert response.results[0].rerank_score == pytest.approx(1.0)
    assert "rerank" in response.results[0].source_strategies


@pytest.mark.asyncio
async def test_advanced_retrieve_mode_d_hybrid_then_rerank() -> None:
    settings = Settings(
        _env_file=None,
        retrieval_rerank_enabled=True,
        retrieval_rerank_model="fake-model",
    )

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

    response = await advanced_retrieve(
        AsyncMock(),
        "OAuth2 Stripe",
        mode_d_preset(),
        recall_k=10,
        top_k_final=2,
        embedder=_FakeEmbedder(),
        reranker=reranker,
        settings=settings,
        vector_repository=_FakeVectorRepository(),
        lexical_repository=_FakeLexicalRepository(),
    )

    assert response.results[0].chunk_id == 201
    assert response.results[0].fusion_score is not None
    assert "rerank" in response.results[0].source_strategies


@pytest.mark.asyncio
async def test_advanced_retrieve_degrades_when_reranker_is_noop() -> None:
    settings = Settings(_env_file=None, retrieval_rerank_enabled=True)

    response = await advanced_retrieve(
        AsyncMock(),
        "OAuth2 backend",
        mode_c_preset(),
        recall_k=10,
        top_k_final=2,
        embedder=_FakeEmbedder(),
        reranker=NoOpReranker(),
        settings=settings,
        vector_repository=_FakeVectorRepository(),
        lexical_repository=_FakeLexicalRepository(),
    )

    assert [row.chunk_id for row in response.results] == [101, 102]
    assert any("no-op" in warning.lower() for warning in response.warnings)


@pytest.mark.asyncio
async def test_advanced_retrieve_honors_rerank_disabled_in_settings() -> None:
    settings = Settings(_env_file=None, retrieval_rerank_enabled=False)

    response = await advanced_retrieve(
        AsyncMock(),
        "OAuth2 backend",
        mode_c_preset(),
        recall_k=10,
        top_k_final=2,
        embedder=_FakeEmbedder(),
        reranker=NoOpReranker(),
        settings=settings,
        vector_repository=_FakeVectorRepository(),
        lexical_repository=_FakeLexicalRepository(),
    )

    assert [row.chunk_id for row in response.results] == [101, 102]
    assert response.results[0].rerank_score is None
    assert any("disabled" in warning.lower() for warning in response.warnings)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("preset", "mode"),
    [
        (mode_a_preset, RetrievalMode.A),
        (mode_b_preset, RetrievalMode.B),
        (mode_c_preset, RetrievalMode.C),
        (mode_d_preset, RetrievalMode.D),
    ],
)
async def test_advanced_presets_match_retrieval_service_ordering(
    preset,
    mode,
) -> None:
    from app.embedding_pipeline.retrieval_service import RetrievalService

    settings = Settings(_env_file=None, retrieval_rerank_enabled=True)
    service = RetrievalService()
    session = AsyncMock()
    embedder = _FakeEmbedder()
    reranker = NoOpReranker()
    vector_repo = _FakeVectorRepository()
    lexical_repo = _FakeLexicalRepository()

    basic = await service.retrieve(
        "OAuth2 Stripe",
        mode=mode,
        recall_k=10,
        top_k_final=3,
        session=session,
        embedder=embedder,
        reranker=reranker,
        settings=settings,
        vector_repository=vector_repo,
        lexical_repository=lexical_repo,
    )
    advanced = await advanced_retrieve(
        session,
        "OAuth2 Stripe",
        preset(),
        recall_k=10,
        top_k_final=3,
        embedder=embedder,
        reranker=reranker,
        settings=settings,
        vector_repository=vector_repo,
        lexical_repository=lexical_repo,
    )

    assert [row.chunk_id for row in advanced.results] == [
        row.chunk_id for row in basic.results
    ]
