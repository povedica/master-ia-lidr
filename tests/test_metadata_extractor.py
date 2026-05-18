"""Unit tests for LLM metadata extraction and merge rules."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.services.metadata_extractor import (
    MetadataExtractionError,
    extract_and_merge_metadata,
    merge_project_metadata,
)
from app.services.sessions import ProjectMetadata


def test_merge_preserves_scalars_and_lists_on_empty_patch() -> None:
    current = ProjectMetadata(
        project_name="Portal",
        mentioned_technologies=["Python"],
    )
    patch = ProjectMetadata()

    merged = merge_project_metadata(current, patch)

    assert merged.project_name == "Portal"
    assert merged.mentioned_technologies == ["Python"]


def test_merge_overwrites_scalar_when_patch_sets_value() -> None:
    current = ProjectMetadata(project_name="Old", assumed_team_size=2)
    patch = ProjectMetadata(project_name="New", assumed_team_size=5)

    merged = merge_project_metadata(current, patch)

    assert merged.project_name == "New"
    assert merged.assumed_team_size == 5


def test_merge_clears_scalar_when_patch_sets_null() -> None:
    current = ProjectMetadata(project_name="Portal", agreed_scope="v1 scope")
    patch = ProjectMetadata(project_name=None, agreed_scope=None)

    merged = merge_project_metadata(current, patch)

    assert merged.project_name is None
    assert merged.agreed_scope is None


def test_merge_appends_list_items_without_case_insensitive_duplicates() -> None:
    current = ProjectMetadata(mentioned_technologies=["Python", "FastAPI"])
    patch = ProjectMetadata(mentioned_technologies=["fastapi", "PostgreSQL"])

    merged = merge_project_metadata(current, patch)

    assert merged.mentioned_technologies == ["Python", "FastAPI", "PostgreSQL"]


def test_merge_removes_technology_when_listed_in_rejected_options() -> None:
    current = ProjectMetadata(
        mentioned_technologies=["React", "Python"],
        rejected_options=[],
    )
    patch = ProjectMetadata(rejected_options=["React"])

    merged = merge_project_metadata(current, patch)

    assert merged.rejected_options == ["React"]
    assert merged.mentioned_technologies == ["Python"]


@pytest.mark.asyncio
async def test_extract_and_merge_metadata_calls_complete_structured() -> None:
    current = ProjectMetadata(project_name="Portal")
    extraction = ProjectMetadata(assumed_team_size=4)

    with patch(
        "app.services.metadata_extractor.complete_structured",
        new_callable=AsyncMock,
        return_value=(extraction, None, "stop"),
    ) as mock_complete:
        merged = await extract_and_merge_metadata(
            current,
            user_turn="Team of four engineers.",
            assistant_turn="Noted, team size 4.",
            litellm_model="gpt-4o-mini",
            chain_provider="openai",
            api_key="test-key",
            timeout_seconds=30.0,
            max_attempts=2,
        )

    assert merged.project_name == "Portal"
    assert merged.assumed_team_size == 4
    mock_complete.assert_awaited_once()


@pytest.mark.asyncio
async def test_extract_and_merge_metadata_raises_on_structured_failure() -> None:
    from app.services.structured_llm_client import StructuredCompletionError

    with patch(
        "app.services.metadata_extractor.complete_structured",
        new_callable=AsyncMock,
        side_effect=StructuredCompletionError("invalid output"),
    ):
        with pytest.raises(MetadataExtractionError):
            await extract_and_merge_metadata(
                ProjectMetadata(),
                user_turn="hello",
                assistant_turn="hi",
                litellm_model="gpt-4o-mini",
                chain_provider="openai",
                api_key="test-key",
                timeout_seconds=30.0,
                max_attempts=2,
            )
