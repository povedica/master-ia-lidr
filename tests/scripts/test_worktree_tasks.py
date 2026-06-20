"""Tests for the worktree task orchestration CLI."""

from __future__ import annotations

from pathlib import Path
import subprocess

import pytest

from scripts.worktree_tasks import (
    ManifestError,
    derive_feature_identity,
    main,
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


def test_plan_command_outputs_order_and_does_not_create_worktrees(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    write_work_item(tmp_path, "feature-042-retrieval-debug-api-foundation.md")
    write_work_item(tmp_path, "feature-043-lexical-fulltext-search-branch.md")
    manifest_path = tmp_path / "manifest.yaml"
    manifest_path.write_text(
        """
defaults:
  worktrees_root: ../master-ia-worktrees
tasks:
  - work_item: docs/work-items/feature-043-lexical-fulltext-search-branch.md
    depends_on: ["042"]
  - work_item: docs/work-items/feature-042-retrieval-debug-api-foundation.md
    depends_on: []
""",
        encoding="utf-8",
    )

    exit_code = main(["plan", "-f", str(manifest_path)], repo_root=tmp_path)

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "042 feature/042-retrieval-debug-api-foundation" in output
    assert "043 feature/043-lexical-fulltext-search-branch" in output
    assert not (tmp_path.parent / "master-ia-worktrees").exists()


def test_prepare_dry_run_outputs_worktree_command_without_mutating(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    write_work_item(tmp_path, "feature-042-retrieval-debug-api-foundation.md")
    manifest_path = tmp_path / "manifest.yaml"
    manifest_path.write_text(
        """
defaults:
  worktrees_root: ../master-ia-worktrees
  base_branch: main
tasks:
  - work_item: docs/work-items/feature-042-retrieval-debug-api-foundation.md
""",
        encoding="utf-8",
    )

    exit_code = main(
        ["prepare", "-f", str(manifest_path), "--only", "042", "--dry-run"],
        repo_root=tmp_path,
    )

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "git worktree add" in output
    assert "feature/042-retrieval-debug-api-foundation" in output
    assert "feature-042-retrieval-debug-api-foundation" in output
    assert not (tmp_path.parent / "master-ia-worktrees").exists()


def test_prepare_writes_instructions_and_symlinks_env_without_logging_secret(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    write_work_item(tmp_path, "feature-042-retrieval-debug-api-foundation.md")
    (tmp_path / ".env").write_text("OPENAI_API_KEY=secret-test-value\n", encoding="utf-8")
    manifest_path = tmp_path / "manifest.yaml"
    manifest_path.write_text(
        """
defaults:
  worktrees_root: worktrees
  env_strategy: symlink
tasks:
  - work_item: docs/work-items/feature-042-retrieval-debug-api-foundation.md
    needs_live_db: true
""",
        encoding="utf-8",
    )

    def fake_run(command: list[str], check: bool) -> subprocess.CompletedProcess[str]:
        Path(command[3]).mkdir(parents=True)
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr("scripts.worktree_tasks.subprocess.run", fake_run)

    exit_code = main(["prepare", "-f", str(manifest_path), "--only", "042"], repo_root=tmp_path)

    worktree_path = tmp_path / "worktrees" / (
        "feature-042-retrieval-debug-api-foundation"
    )
    output = capsys.readouterr().out
    assert exit_code == 0
    assert (worktree_path / "INSTRUCTIONS.md").read_text(encoding="utf-8").startswith(
        "# Worktree task instructions",
    )
    assert "/start-task docs/work-items/feature-042-retrieval-debug-api-foundation.md" in (
        worktree_path / "INSTRUCTIONS.md"
    ).read_text(encoding="utf-8")
    assert (worktree_path / ".env").is_symlink()
    assert "secret-test-value" not in output


def test_status_reports_prepared_task_from_persisted_state(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    write_work_item(tmp_path, "feature-042-retrieval-debug-api-foundation.md")
    manifest_path = tmp_path / "manifest.yaml"
    manifest_path.write_text(
        """
defaults:
  worktrees_root: worktrees
tasks:
  - work_item: docs/work-items/feature-042-retrieval-debug-api-foundation.md
""",
        encoding="utf-8",
    )

    def fake_run(command: list[str], check: bool) -> subprocess.CompletedProcess[str]:
        Path(command[3]).mkdir(parents=True)
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr("scripts.worktree_tasks.subprocess.run", fake_run)
    assert main(["prepare", "-f", str(manifest_path), "--only", "042"], repo_root=tmp_path) == 0

    exit_code = main(["status", "-f", str(manifest_path)], repo_root=tmp_path)

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "042" in output
    assert "prepared" in output
    assert "feature/042-retrieval-debug-api-foundation" in output


def test_cleanup_dry_run_outputs_remove_command_without_deleting_worktree(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    write_work_item(tmp_path, "feature-042-retrieval-debug-api-foundation.md")
    manifest_path = tmp_path / "manifest.yaml"
    manifest_path.write_text(
        """
defaults:
  worktrees_root: worktrees
tasks:
  - work_item: docs/work-items/feature-042-retrieval-debug-api-foundation.md
""",
        encoding="utf-8",
    )

    def fake_run(command: list[str], check: bool) -> subprocess.CompletedProcess[str]:
        Path(command[3]).mkdir(parents=True)
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr("scripts.worktree_tasks.subprocess.run", fake_run)
    assert main(["prepare", "-f", str(manifest_path), "--only", "042"], repo_root=tmp_path) == 0

    worktree_path = tmp_path / "worktrees" / "feature-042-retrieval-debug-api-foundation"
    exit_code = main(
        ["cleanup", "-f", str(manifest_path), "--only", "042", "--dry-run"],
        repo_root=tmp_path,
    )

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "git worktree remove" in output
    assert str(worktree_path) in output
    assert worktree_path.exists()
