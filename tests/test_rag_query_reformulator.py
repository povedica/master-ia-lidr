"""Unit tests for RAG query reformulation and search text composition."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.config import Settings
from app.schemas.estimation_query import EstimationQuery, compose_search_text
from app.services.llm_chain import LitellmChainProvider
from app.services.rag_query_reformulator import reformulate_query


def _providers() -> list[LitellmChainProvider]:
    return [
        LitellmChainProvider(
            name="openai",
            litellm_model="gpt-4o-mini",
            api_key="test-key",
            timeout_seconds=30.0,
        )
    ]


def test_compose_search_text_question_only_pass_through() -> None:
    query = EstimationQuery(
        question="OAuth2 login integration for CRM",
        search_facets=[],
        component_hints=[],
        sector_filters=[],
    )

    assert compose_search_text(query) == "OAuth2 login integration for CRM"


def test_compose_search_text_merges_facets_deterministically() -> None:
    query = EstimationQuery(
        question="CRM integration estimate",
        search_facets=["OAuth2", "single sign-on"],
        component_hints=["authentication", "user management"],
        sector_filters=["fintech"],
    )

    text = compose_search_text(query)

    assert text == (
        "CRM integration estimate | "
        "facets: OAuth2, single sign-on | "
        "components: authentication, user management | "
        "sectors: fintech"
    )


def test_compose_search_text_omits_empty_optional_sections() -> None:
    query = EstimationQuery(
        question="Stripe checkout",
        search_facets=["payment gateway"],
        component_hints=[],
        sector_filters=[],
    )

    assert compose_search_text(query) == "Stripe checkout | facets: payment gateway"


def test_estimation_query_rejects_blank_question() -> None:
    with pytest.raises(ValueError, match="question must not be empty"):
        EstimationQuery(
            question="   ",
            search_facets=[],
            component_hints=[],
            sector_filters=[],
        )


@pytest.mark.asyncio
async def test_reformulate_query_pass_through_without_transcript_when_disabled() -> None:
    settings = Settings(_env_file=None, reformulation_enabled=False)

    query = await reformulate_query(
        "OAuth platform integration",
        settings=settings,
        providers=_providers(),
    )

    assert query == EstimationQuery(
        question="OAuth platform integration",
        search_facets=[],
        component_hints=[],
        sector_filters=[],
    )


@pytest.mark.asyncio
async def test_reformulate_query_uses_llm_when_transcript_provided() -> None:
    settings = Settings(_env_file=None, reformulation_enabled=False)
    llm_query = EstimationQuery(
        question="CRM SSO estimate",
        search_facets=["OAuth2", "CRM"],
        component_hints=["authentication"],
        sector_filters=["saas"],
    )

    with patch(
        "app.services.rag_query_reformulator.complete_structured",
        new=AsyncMock(return_value=(llm_query, None, "stop")),
    ) as mock_complete:
        query = await reformulate_query(
            "CRM SSO estimate",
            transcript="We need OAuth for our CRM login.",
            settings=settings,
            providers=_providers(),
        )

    mock_complete.assert_awaited_once()
    assert query.search_facets == ["OAuth2", "CRM"]
    assert query.component_hints == ["authentication"]


@pytest.mark.asyncio
async def test_reformulate_query_uses_llm_when_enabled_without_transcript() -> None:
    settings = Settings(_env_file=None, reformulation_enabled=True)
    llm_query = EstimationQuery(
        question="Stripe checkout",
        search_facets=["payments"],
        component_hints=["checkout"],
        sector_filters=[],
    )

    with patch(
        "app.services.rag_query_reformulator.complete_structured",
        new=AsyncMock(return_value=(llm_query, None, "stop")),
    ) as mock_complete:
        query = await reformulate_query(
            "Stripe checkout",
            settings=settings,
            providers=_providers(),
        )

    mock_complete.assert_awaited_once()
    assert query.search_facets == ["payments"]

