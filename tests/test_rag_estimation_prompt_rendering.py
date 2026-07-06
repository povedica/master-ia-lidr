"""Tests for RAG estimation prompt rendering (FR-06)."""

from __future__ import annotations

from app.services.rag_estimation_prompt_rendering import render_rag_estimation_prompt


def test_rag_prompt_includes_citation_and_insufficiency_rules() -> None:
    rendered = render_rag_estimation_prompt(
        question="E-commerce with Stripe and OAuth2",
        prompt_block="[CHUNK START]\nchunk_id: 42\n[CHUNK END]",
    )

    combined = rendered.system_prompt + rendered.user_prompt
    assert "Per-line attribution" in combined or "per-line attribution" in combined.lower()
    assert "Literal evidence" in combined or "literal evidence" in combined.lower()
    assert "grounded=false" in combined
    assert "chunk_id: 42" in combined
    assert rendered.prompt_version == "estimation/rag/v1"
