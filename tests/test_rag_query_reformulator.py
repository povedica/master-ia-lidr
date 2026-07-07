"""Unit tests for RAG query reformulation and search text composition."""

from __future__ import annotations

import pytest

from app.schemas.estimation_query import EstimationQuery, compose_search_text


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
