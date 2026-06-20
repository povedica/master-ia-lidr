"""Orchestrate feature worktrees for parallel task execution."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from graphlib import CycleError, TopologicalSorter
import json
from pathlib import Path
import re
import sys
from typing import Any

import yaml

FEATURE_WORK_ITEM_PATTERN = re.compile(
    r"^docs/work-items/feature-(?P<feature_id>\d{3})-(?P<slug>[a-z0-9]+(?:-[a-z0-9]+)*)\.md$",
)


class ManifestError(ValueError):
    """Raised when a worktree task manifest is invalid."""


@dataclass(frozen=True)
class FeatureIdentity:
    feature_id: str
    slug: str
    work_item: Path
    branch: str
    prompt: str


@dataclass(frozen=True)
class WorktreeTask:
    feature_id: str
    slug: str
    work_item: Path
    branch: str
    prompt: str
    worktree_path: Path
    depends_on: tuple[str, ...]
    needs_live_db: bool
    mode: str
    mutex_group: str | None


@dataclass(frozen=True)
class WorktreePlan:
    tasks_by_id: dict[str, WorktreeTask]
    execution_order: tuple[WorktreeTask, ...]


def derive_feature_identity(work_item: Path) -> FeatureIdentity:
    """Derive task identity and branch metadata from a feature work item path."""
    normalized_path = work_item.as_posix()
    match = FEATURE_WORK_ITEM_PATTERN.match(normalized_path)
    if match is None:
        raise ManifestError(
            "Work item must match docs/work-items/feature-NNN-<slug>.md",
        )

    feature_id = match.group("feature_id")
    slug = match.group("slug")
    branch = f"feature/{feature_id}-{slug}"
    prompt = f"/start-task {normalized_path}"
    return FeatureIdentity(
        feature_id=feature_id,
        slug=slug,
        work_item=work_item,
        branch=branch,
        prompt=prompt,
    )


def parse_manifest_data(data: dict[str, Any], *, repo_root: Path) -> WorktreePlan:
    """Validate manifest data and return an executable task plan."""
    defaults = data.get("defaults", {})
    raw_tasks = data.get("tasks")
    if not isinstance(raw_tasks, list) or not raw_tasks:
        raise ManifestError("Manifest must include a non-empty tasks list")

    worktrees_root = _resolve_worktrees_root(
        repo_root=repo_root,
        raw_path=defaults.get("worktrees_root", "../master-ia-worktrees"),
    )
    default_mode = defaults.get("mode", "prepare")

    tasks_by_id: dict[str, WorktreeTask] = {}
    dependency_refs: dict[str, tuple[str, ...]] = {}

    for raw_task in raw_tasks:
        if not isinstance(raw_task, dict):
            raise ManifestError("Each task must be a mapping")

        task = _parse_task(
            raw_task,
            repo_root=repo_root,
            worktrees_root=worktrees_root,
            default_mode=default_mode,
        )
        if task.feature_id in tasks_by_id:
            raise ManifestError(f"Duplicate task id: {task.feature_id}")

        tasks_by_id[task.feature_id] = task
        dependency_refs[task.feature_id] = task.depends_on

    graph = _build_dependency_graph(dependency_refs, tasks_by_id)
    try:
        ordered_ids = tuple(TopologicalSorter(graph).static_order())
    except CycleError as exc:
        raise ManifestError("Dependency graph contains a cycle") from exc

    return WorktreePlan(
        tasks_by_id=tasks_by_id,
        execution_order=tuple(tasks_by_id[feature_id] for feature_id in ordered_ids),
    )


def load_manifest_file(manifest_path: Path) -> dict[str, Any]:
    """Load a YAML or JSON manifest file."""
    try:
        raw_content = manifest_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ManifestError(f"Unable to read manifest: {manifest_path}") from exc

    if manifest_path.suffix.lower() == ".json":
        loaded = json.loads(raw_content)
    else:
        loaded = yaml.safe_load(raw_content)

    if not isinstance(loaded, dict):
        raise ManifestError("Manifest root must be a mapping")
    return loaded


def main(argv: list[str] | None = None, *, repo_root: Path | None = None) -> int:
    """Run the worktree task CLI."""
    parser = argparse.ArgumentParser(
        description="Prepare and inspect feature worktree task plans.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    plan_parser = subparsers.add_parser(
        "plan",
        help="Validate a manifest and print execution order without mutations.",
    )
    plan_parser.add_argument("-f", "--file", required=True, help="Manifest YAML/JSON path")

    args = parser.parse_args(argv)
    root = repo_root or Path.cwd()

    try:
        if args.command == "plan":
            manifest = load_manifest_file(Path(args.file))
            plan = parse_manifest_data(manifest, repo_root=root)
            _print_plan(plan)
            return 0
    except ManifestError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    parser.error(f"Unsupported command: {args.command}")
    return 2


def _print_plan(plan: WorktreePlan) -> None:
    for task in plan.execution_order:
        dependencies = ",".join(task.depends_on) if task.depends_on else "-"
        print(
            f"{task.feature_id} {task.branch} "
            f"worktree={task.worktree_path} depends_on={dependencies} "
            f"mode={task.mode} needs_live_db={str(task.needs_live_db).lower()}",
        )


def _parse_task(
    raw_task: dict[str, Any],
    *,
    repo_root: Path,
    worktrees_root: Path,
    default_mode: str,
) -> WorktreeTask:
    raw_work_item = raw_task.get("work_item")
    if not isinstance(raw_work_item, str):
        raise ManifestError("Task work_item must be a string")

    work_item = Path(raw_work_item)
    identity = derive_feature_identity(work_item)
    if not (repo_root / work_item).is_file():
        raise ManifestError(f"Work item does not exist: {work_item.as_posix()}")

    mode = raw_task.get("mode", default_mode)
    if mode not in {"prepare", "sdk"}:
        raise ManifestError(f"Unsupported mode for {identity.feature_id}: {mode}")

    depends_on = tuple(_normalize_dependency(dep) for dep in raw_task.get("depends_on", []))
    worktree_path = worktrees_root / f"feature-{identity.feature_id}-{identity.slug}"
    mutex_group = raw_task.get("mutex_group")
    if mutex_group is not None and not isinstance(mutex_group, str):
        raise ManifestError("mutex_group must be a string when provided")

    return WorktreeTask(
        feature_id=identity.feature_id,
        slug=identity.slug,
        work_item=identity.work_item,
        branch=identity.branch,
        prompt=identity.prompt,
        worktree_path=worktree_path,
        depends_on=depends_on,
        needs_live_db=bool(raw_task.get("needs_live_db", False)),
        mode=mode,
        mutex_group=mutex_group,
    )


def _resolve_worktrees_root(*, repo_root: Path, raw_path: str | Path) -> Path:
    root = Path(raw_path)
    if not root.is_absolute():
        root = repo_root / root
    return root.resolve()


def _normalize_dependency(raw_dependency: Any) -> str:
    if isinstance(raw_dependency, int):
        return f"{raw_dependency:03d}"
    if not isinstance(raw_dependency, str):
        raise ManifestError("Dependencies must be feature ids or work item paths")

    if raw_dependency.isdigit():
        return raw_dependency.zfill(3)

    return derive_feature_identity(Path(raw_dependency)).feature_id


def _build_dependency_graph(
    dependency_refs: dict[str, tuple[str, ...]],
    tasks_by_id: dict[str, WorktreeTask],
) -> dict[str, set[str]]:
    graph: dict[str, set[str]] = {}
    for feature_id, dependencies in dependency_refs.items():
        graph[feature_id] = set()
        for dependency in dependencies:
            if dependency not in tasks_by_id:
                raise ManifestError(
                    f"Unknown dependency for {feature_id}: {dependency}",
                )
            graph[feature_id].add(dependency)
    return graph


if __name__ == "__main__":
    raise SystemExit(main())
