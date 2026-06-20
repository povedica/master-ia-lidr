"""Tests for the worktree task orchestration CLI."""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.worktree_tasks import (
    ManifestError,
    derive_feature_identity,
    parse_manifest_data,
)


def write_work_item(repo_root: Path, filename: str) -> Path:
    work_items_dir = repo_root / "docs" / "work-items"
    work_items_dir.mkdir(parents=True, exist_ok=True)
    work_item = work_items_dir / filename
    work_item.write_text("# Feature: Test\n", encoding="utf-8")
    return work_item


def test_derive_feature_identity_from_work_item_path() -> None:
    identity = derive_feature_identity(
        Path("docs/work-items/feature-049-parallel-worktree-task-orchestrator.md"),
    )

    assert identity.feature_id == "049"
    assert identity.slug == "parallel-worktree-task-orchestrator"
    assert identity.branch == "feature/049-parallel-worktree-task-orchestrator"
    assert identity.prompt == (
        "/start-task docs/work-items/feature-049-parallel-worktree-task-orchestrator.md"
    )


def test_derive_feature_identity_rejects_legacy_feature_names() -> None:
    with pytest.raises(ManifestError, match="feature-NNN"):
        derive_feature_identity(Path("docs/work-items/feature-worktree-task-orchestrator.md"))


def test_parse_manifest_data_applies_defaults_and_orders_dependencies(tmp_path: Path) -> None:
    write_work_item(tmp_path, "feature-042-retrieval-debug-api-foundation.md")
    write_work_item(tmp_path, "feature-043-lexical-fulltext-search-branch.md")
    data = {
        "defaults": {
            "worktrees_root": "../master-ia-worktrees",
            "base_branch": "main",
            "max_parallel": 2,
            "env_strategy": "symlink",
        },
        "tasks": [
            {
                "work_item": "docs/work-items/feature-043-lexical-fulltext-search-branch.md",
                "depends_on": ["042"],
                "needs_live_db": True,
            },
            {
                "work_item": "docs/work-items/feature-042-retrieval-debug-api-foundation.md",
                "depends_on": [],
            },
        ],
    }

    plan = parse_manifest_data(data, repo_root=tmp_path)

    assert [task.feature_id for task in plan.execution_order] == ["042", "043"]
    lexical = plan.tasks_by_id["043"]
    assert lexical.mode == "prepare"
    assert lexical.needs_live_db is True
    assert lexical.branch == "feature/043-lexical-fulltext-search-branch"
    assert lexical.worktree_path == tmp_path.parent / "master-ia-worktrees" / (
        "feature-043-lexical-fulltext-search-branch"
    )


def test_parse_manifest_data_rejects_missing_dependencies(tmp_path: Path) -> None:
    write_work_item(tmp_path, "feature-043-lexical-fulltext-search-branch.md")
    data = {
        "tasks": [
            {
                "work_item": "docs/work-items/feature-043-lexical-fulltext-search-branch.md",
                "depends_on": ["042"],
            },
        ],
    }

    with pytest.raises(ManifestError, match="Unknown dependency"):
        parse_manifest_data(data, repo_root=tmp_path)


def test_parse_manifest_data_rejects_dependency_cycles(tmp_path: Path) -> None:
    write_work_item(tmp_path, "feature-042-retrieval-debug-api-foundation.md")
    write_work_item(tmp_path, "feature-043-lexical-fulltext-search-branch.md")
    data = {
        "tasks": [
            {
                "work_item": "docs/work-items/feature-042-retrieval-debug-api-foundation.md",
                "depends_on": ["043"],
            },
            {
                "work_item": "docs/work-items/feature-043-lexical-fulltext-search-branch.md",
                "depends_on": ["042"],
            },
        ],
    }

    with pytest.raises(ManifestError, match="cycle"):
        parse_manifest_data(data, repo_root=tmp_path)
