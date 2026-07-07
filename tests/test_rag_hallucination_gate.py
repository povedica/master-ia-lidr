"""Unit tests for RAG hallucination gate (feature-060)."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.config import Settings
from app.schemas.hallucination_report import (
    HallucinationJudgeBatchResult,
    HallucinationJudgeLineResult,
    HallucinationLineGrade,
)
from app.schemas.rag_estimation_result import RagEstimationLineItem, RagEstimationResult, SourceReference
from app.services.llm_chain import LitellmChainProvider
from app.services.rag_hallucination_gate import gate_line, judge_estimate, numeric_anchor
from app.services.structured_llm_client import StructuredCompletionError

_INFLATED_HOURS_CHUNK = (
    "OAuth2 login integration scope — prior budget line: 8 hours "
    "for authentication module including SSO callbacks."
)


def test_numeric_anchor_extracts_hour_patterns() -> None:
    chunks = [
        "Authentication module: 8 hours for OAuth2 login flow.",
        "Stripe checkout integration budgeted at 12.5 hrs.",
        "No numeric budget reference in this chunk.",
        "Quick spike: 3h for webhook wiring.",
    ]

    anchors = numeric_anchor(chunks)

    assert anchors == [3.0, 8.0, 12.5]


def test_numeric_anchor_empty_when_no_hour_like_numbers() -> None:
    anchors = numeric_anchor(
        [
            "OAuth2 login integration scope without hour figures.",
            "Discuss SSO callbacks and token refresh only.",
        ]
    )

    assert anchors == []


def test_gate_line_grounded_within_tolerance_of_anchor_max() -> None:
    grade = gate_line(line_hours=9.0, anchor_hours=[8.0], tolerance=0.25)

    assert grade == HallucinationLineGrade.GROUNDED


def test_gate_line_degraded_when_hours_far_above_anchor_max() -> None:
    grade = gate_line(line_hours=80.0, anchor_hours=[8.0], tolerance=0.25)

    assert grade == HallucinationLineGrade.DEGRADED


def test_gate_line_insufficient_when_no_anchors() -> None:
    grade = gate_line(line_hours=12.0, anchor_hours=[])

    assert grade == HallucinationLineGrade.INSUFFICIENT


def test_inflated_hours_fixture_marks_line_degraded() -> None:
    """AC-11 from feature-053: canned chunk vs inflated line hours."""

    anchors = numeric_anchor([_INFLATED_HOURS_CHUNK])

    assert anchors == [8.0]
    assert gate_line(line_hours=80.0, anchor_hours=anchors) == HallucinationLineGrade.DEGRADED


def _providers() -> list[LitellmChainProvider]:
    return [
        LitellmChainProvider(
            name="openai",
            litellm_model="gpt-4o-mini",
            api_key="test-key",
            timeout_seconds=30.0,
        )
    ]


def _grounded_line(
    *,
    component: str = "OAuth2 login",
    hours: float = 8.0,
    rationale: str = "Matches prior authentication budget line.",
) -> RagEstimationLineItem:
    return RagEstimationLineItem(
        component=component,
        hours=hours,
        rationale=rationale,
        grounded=True,
        sources=[
            SourceReference(
                chunk_id=42,
                document_id=7,
                evidence="OAuth2 login integration scope",
            )
        ],
    )


def _estimate(*lines: RagEstimationLineItem) -> RagEstimationResult:
    return RagEstimationResult(
        summary="Hallucination gate judge test estimate with grounded line items.",
        line_items=list(lines),
        total_hours=sum(line.hours for line in lines),
    )


@pytest.mark.asyncio
async def test_judge_estimate_empty_line_items_skips_llm() -> None:
    settings = Settings(_env_file=None)
    estimate = _estimate()

    with patch(
        "app.services.rag_hallucination_gate.complete_structured",
        new=AsyncMock(),
    ) as mock_complete:
        results = await judge_estimate(
            estimate,
            chunk_texts=[_INFLATED_HOURS_CHUNK],
            settings=settings,
            providers=_providers(),
        )

    mock_complete.assert_not_awaited()
    assert results == []


@pytest.mark.asyncio
async def test_judge_estimate_returns_structured_grades_from_llm() -> None:
    settings = Settings(_env_file=None)
    estimate = _estimate(
        _grounded_line(hours=8.0),
        _grounded_line(component="SSO callbacks", hours=80.0),
    )
    batch = HallucinationJudgeBatchResult(
        lines=[
            HallucinationJudgeLineResult(index=0, grade=HallucinationLineGrade.GROUNDED),
            HallucinationJudgeLineResult(index=1, grade=HallucinationLineGrade.DEGRADED),
        ]
    )

    with patch(
        "app.services.rag_hallucination_gate.complete_structured",
        new=AsyncMock(return_value=(batch, None, "stop")),
    ) as mock_complete:
        results = await judge_estimate(
            estimate,
            chunk_texts=[_INFLATED_HOURS_CHUNK],
            settings=settings,
            providers=_providers(),
        )

    mock_complete.assert_awaited_once()
    call_kwargs = mock_complete.await_args.kwargs
    assert call_kwargs["response_model"] is HallucinationJudgeBatchResult
    assert "8.0" in call_kwargs["user_prompt"]
    assert results == batch.lines


@pytest.mark.asyncio
async def test_judge_estimate_marks_insufficient_on_llm_failure() -> None:
    settings = Settings(_env_file=None)
    estimate = _estimate(_grounded_line(hours=8.0))

    with patch(
        "app.services.rag_hallucination_gate.complete_structured",
        new=AsyncMock(side_effect=StructuredCompletionError("schema mismatch")),
    ):
        results = await judge_estimate(
            estimate,
            chunk_texts=[_INFLATED_HOURS_CHUNK],
            settings=settings,
            providers=_providers(),
        )

    assert results == [
        HallucinationJudgeLineResult(index=0, grade=HallucinationLineGrade.INSUFFICIENT)
    ]


@pytest.mark.asyncio
async def test_judge_estimate_marks_insufficient_when_no_provider() -> None:
    settings = Settings(_env_file=None)
    estimate = _estimate(_grounded_line(hours=8.0))

    with patch(
        "app.services.rag_hallucination_gate.complete_structured",
        new=AsyncMock(),
    ) as mock_complete:
        results = await judge_estimate(
            estimate,
            chunk_texts=[_INFLATED_HOURS_CHUNK],
            settings=settings,
            providers=[],
        )

    mock_complete.assert_not_awaited()
    assert results == [
        HallucinationJudgeLineResult(index=0, grade=HallucinationLineGrade.INSUFFICIENT)
    ]
