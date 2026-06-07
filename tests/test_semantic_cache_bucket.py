"""Deterministic semantic cache bucket tests."""

from __future__ import annotations

from app.config import Settings
from app.schemas.estimation_request import EstimationRequest
from app.services.estimation_request_render import render_estimation_assessment_surface
from app.services.semantic_cache.bucket import (
    build_semantic_cache_bucket,
    build_vector_text_surface,
)
from tests.estimation_fixtures import minimal_estimation_request_dict


def test_bucket_stable_for_same_inputs() -> None:
    settings = Settings()
    body = EstimationRequest.model_validate(minimal_estimation_request_dict(evaluate=False))
    b1 = build_semantic_cache_bucket(
        request=body,
        settings=settings,
        prompt_version="estimation/v1",
        examples_version="ex-v1",
        output_schema_version="1",
        guardrail_rules_version="registry-default",
        operation="estimation_v2",
        tenant_id="default",
    )
    b2 = build_semantic_cache_bucket(
        request=body,
        settings=settings,
        prompt_version="estimation/v1",
        examples_version="ex-v1",
        output_schema_version="1",
        guardrail_rules_version="registry-default",
        operation="estimation_v2",
        tenant_id="default",
    )
    assert b1.bucket_hash == b2.bucket_hash


def test_prompt_version_change_changes_bucket() -> None:
    settings = Settings()
    body = EstimationRequest.model_validate(minimal_estimation_request_dict(evaluate=False))
    a = build_semantic_cache_bucket(
        request=body,
        settings=settings,
        prompt_version="estimation/v1",
        examples_version="ex",
        output_schema_version="1",
        guardrail_rules_version="registry-default",
        operation="estimation_v2",
        tenant_id="default",
    )
    b = build_semantic_cache_bucket(
        request=body,
        settings=settings,
        prompt_version="estimation/v2",
        examples_version="ex",
        output_schema_version="1",
        guardrail_rules_version="registry-default",
        operation="estimation_v2",
        tenant_id="default",
    )
    assert a.bucket_hash != b.bucket_hash


def test_vector_surface_includes_free_text() -> None:
    body = EstimationRequest.model_validate(minimal_estimation_request_dict(evaluate=False))
    surface = render_estimation_assessment_surface(body)
    text = build_vector_text_surface(request=body, assessment_surface=surface)
    assert body.project_summary[:10] in text
    assert body.project_description[:20] in text
