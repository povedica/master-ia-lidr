"""Usage and cost detail mappers for Langfuse generations."""

from __future__ import annotations

import pytest

from app.services.observability.usage_cost import cost_details_from_estimate, openai_usage_details
from app.services.llm_types import UsageInfo


def test_openai_usage_details_maps_standard_tokens() -> None:
    details = openai_usage_details(
        {
            "prompt_tokens": 100,
            "completion_tokens": 50,
            "total_tokens": 150,
        }
    )
    assert details == {
        "prompt_tokens": 100,
        "completion_tokens": 50,
        "total_tokens": 150,
    }


def test_openai_usage_details_from_usage_info() -> None:
    usage = UsageInfo(
        prompt_tokens=10,
        completion_tokens=5,
        total_tokens=15,
        preprocessing_input_tokens=2,
        preprocessing_output_tokens=1,
    )
    details = openai_usage_details(usage)
    assert details["prompt_tokens"] == 10
    assert details["preprocessing_input_tokens"] == 2


def test_openai_usage_details_omits_zero_preprocessing() -> None:
    details = openai_usage_details(
        {
            "prompt_tokens": 1,
            "completion_tokens": 1,
            "total_tokens": 2,
            "preprocessing_input_tokens": 0,
            "preprocessing_output_tokens": 0,
        }
    )
    assert "preprocessing_input_tokens" not in details
    assert "preprocessing_output_tokens" not in details


def test_cost_details_from_estimate_returns_total() -> None:
    assert cost_details_from_estimate(0.0123) == {"total": 0.0123}


def test_cost_details_from_estimate_none_when_unknown() -> None:
    assert cost_details_from_estimate(None) is None


def test_cost_details_from_estimate_rejects_negative() -> None:
    with pytest.raises(ValueError, match="negative"):
        cost_details_from_estimate(-0.01)
