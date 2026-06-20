"""Orchestrate feature worktrees for parallel task execution."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from graphlib import CycleError, TopologicalSorter
import json
from pathlib import Path
import re
import shutil
import subprocess
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
    base_branch: str
    env_strategy: str
    worktrees_root: Path
    max_parallel: int


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
    base_branch = str(defaults.get("base_branch", "main"))
    env_strategy = str(defaults.get("env_strategy", "symlink"))
    if env_strategy not in {"symlink", "copy"}:
        raise ManifestError("env_strategy must be 'symlink' or 'copy'")
    max_parallel = int(defaults.get("max_parallel", 2))
    if max_parallel < 1:
        raise ManifestError("max_parallel must be at least 1")
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
        base_branch=base_branch,
        env_strategy=env_strategy,
        worktrees_root=worktrees_root,
        max_parallel=max_parallel,
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

    prepare_parser = subparsers.add_parser(
        "prepare",
        help="Create or preview worktree preparation commands.",
    )
    prepare_parser.add_argument("-f", "--file", required=True, help="Manifest YAML/JSON path")
    prepare_parser.add_argument(
        "--only",
        help="Comma-separated feature ids to prepare, e.g. 042,043.",
    )
    prepare_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print planned commands without creating worktrees.",
    )
    prepare_parser.add_argument(
        "--reuse-existing",
        action="store_true",
        help="Treat existing worktree paths as reusable instead of failing.",
    )

    status_parser = subparsers.add_parser(
        "status",
        help="Show persisted worktree task status.",
    )
    status_parser.add_argument("-f", "--file", required=True, help="Manifest YAML/JSON path")

    cleanup_parser = subparsers.add_parser(
        "cleanup",
        help="Remove prepared worktrees conservatively.",
    )
    cleanup_parser.add_argument("-f", "--file", required=True, help="Manifest YAML/JSON path")
    cleanup_parser.add_argument("--only", help="Comma-separated feature ids to clean up.")
    cleanup_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print planned removals without deleting worktrees.",
    )
    cleanup_parser.add_argument(
        "--force",
        action="store_true",
        help="Allow cleanup of dirty or unmerged worktrees.",
    )

    run_parser = subparsers.add_parser(
        "run",
        help="Preview future Cursor SDK task execution.",
    )
    run_parser.add_argument("-f", "--file", required=True, help="Manifest YAML/JSON path")
    run_parser.add_argument("--only", help="Comma-separated feature ids to run.")
    run_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print SDK prompts without launching agents.",
    )

    args = parser.parse_args(argv)
    root = repo_root or Path.cwd()

    try:
        if args.command == "plan":
            manifest = load_manifest_file(Path(args.file))
            plan = parse_manifest_data(manifest, repo_root=root)
            _print_plan(plan)
            return 0
        if args.command == "prepare":
            manifest = load_manifest_file(Path(args.file))
            plan = parse_manifest_data(manifest, repo_root=root)
            selected_tasks = _select_tasks(plan, args.only)
            _prepare_tasks(
                selected_tasks,
                repo_root=root,
                state_path=_state_path(plan),
                base_branch=plan.base_branch,
                env_strategy=plan.env_strategy,
                dry_run=args.dry_run,
                reuse_existing=args.reuse_existing,
            )
            return 0
        if args.command == "status":
            manifest = load_manifest_file(Path(args.file))
            plan = parse_manifest_data(manifest, repo_root=root)
            _print_status(plan)
            return 0
        if args.command == "cleanup":
            manifest = load_manifest_file(Path(args.file))
            plan = parse_manifest_data(manifest, repo_root=root)
            selected_tasks = _select_tasks(plan, args.only)
            _cleanup_tasks(
                selected_tasks,
                state_path=_state_path(plan),
                dry_run=args.dry_run,
                force=args.force,
            )
            return 0
        if args.command == "run":
            manifest = load_manifest_file(Path(args.file))
            plan = parse_manifest_data(manifest, repo_root=root)
            selected_tasks = _select_tasks(plan, args.only)
            _run_sdk_tasks(selected_tasks, max_parallel=plan.max_parallel, dry_run=args.dry_run)
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


def _select_tasks(plan: WorktreePlan, only: str | None) -> tuple[WorktreeTask, ...]:
    if only is None:
        return plan.execution_order

    requested_ids = tuple(_normalize_dependency(value.strip()) for value in only.split(","))
    missing_ids = [feature_id for feature_id in requested_ids if feature_id not in plan.tasks_by_id]
    if missing_ids:
        raise ManifestError(f"Unknown task id: {', '.join(missing_ids)}")
    return tuple(plan.tasks_by_id[feature_id] for feature_id in requested_ids)


def _prepare_tasks(
    tasks: tuple[WorktreeTask, ...],
    *,
    repo_root: Path,
    state_path: Path,
    base_branch: str,
    env_strategy: str,
    dry_run: bool,
    reuse_existing: bool,
) -> None:
    state = _load_state(state_path)
    for task in tasks:
        command = _worktree_add_command(task, base_branch=base_branch)
        print(" ".join(command))
        if dry_run:
            continue

        if task.worktree_path.exists():
            if reuse_existing:
                print(f"reuse existing worktree: {task.worktree_path}")
                _write_instructions(task)
                _bootstrap_env(task, repo_root=repo_root, env_strategy=env_strategy)
                _record_status(state, task, status="prepared")
                continue
            raise ManifestError(
                f"Worktree path already exists: {task.worktree_path}. "
                "Use --reuse-existing to keep it.",
            )

        task.worktree_path.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(command, check=True)
        _write_instructions(task)
        _bootstrap_env(task, repo_root=repo_root, env_strategy=env_strategy)
        _record_status(state, task, status="prepared")
    if not dry_run:
        _save_state(state_path, state)


def _worktree_add_command(task: WorktreeTask, *, base_branch: str) -> list[str]:
    return [
        "git",
        "worktree",
        "add",
        str(task.worktree_path),
        "-b",
        task.branch,
        base_branch,
    ]


def _cleanup_tasks(
    tasks: tuple[WorktreeTask, ...],
    *,
    state_path: Path,
    dry_run: bool,
    force: bool,
) -> None:
    state = _load_state(state_path)
    for task in tasks:
        command = _worktree_remove_command(task)
        print(" ".join(command))
        if dry_run:
            continue

        if not task.worktree_path.exists():
            raise ManifestError(f"Worktree path does not exist: {task.worktree_path}")
        if not force:
            _assert_worktree_clean(task)

        subprocess.run(command, check=True)
        _record_status(state, task, status="done")

    if not dry_run:
        subprocess.run(["git", "worktree", "prune"], check=True)
        _save_state(state_path, state)


def _run_sdk_tasks(
    tasks: tuple[WorktreeTask, ...],
    *,
    max_parallel: int,
    dry_run: bool,
) -> None:
    print(f"max_parallel={max_parallel}")
    for task in tasks:
        print(f"{task.feature_id} prompt={task.prompt} cwd={task.worktree_path}")

    if dry_run:
        print("SDK runner is not implemented; dry-run only. Use prepare/manual fallback.")
        return

    raise ManifestError(
        "SDK runner is not implemented yet. Re-run with --dry-run or use prepare/manual fallback.",
    )


def _worktree_remove_command(task: WorktreeTask) -> list[str]:
    return ["git", "worktree", "remove", str(task.worktree_path)]


def _assert_worktree_clean(task: WorktreeTask) -> None:
    status_result = subprocess.run(
        ["git", "-C", str(task.worktree_path), "status", "--short"],
        capture_output=True,
        check=True,
        text=True,
    )
    if status_result.stdout.strip():
        raise ManifestError(
            f"Worktree has uncommitted changes: {task.worktree_path}. Use --force to override.",
        )


def _write_instructions(task: WorktreeTask) -> None:
    live_db_note = (
        "- This task is marked `needs_live_db=true`; run live database checks serially.\n"
        if task.needs_live_db
        else "- This task is not marked as requiring live database checks.\n"
    )
    content = (
        "# Worktree task instructions\n\n"
        f"- Work item: `{task.work_item.as_posix()}`\n"
        f"- Branch: `{task.branch}`\n"
        f"- Manual Cursor command: `{task.prompt}`\n"
        f"- Worktree path: `{task.worktree_path}`\n"
        f"{live_db_note}\n"
        "Do not commit `.env`, local logs, or generated runtime artifacts.\n"
    )
    (task.worktree_path / "INSTRUCTIONS.md").write_text(content, encoding="utf-8")


def _bootstrap_env(task: WorktreeTask, *, repo_root: Path, env_strategy: str) -> None:
    source_env = repo_root / ".env"
    target_env = task.worktree_path / ".env"
    if not source_env.exists():
        print(f"warning: missing local .env at {source_env}; skipping env bootstrap")
        return
    if target_env.exists() or target_env.is_symlink():
        print(f"env already present: {target_env}")
        return

    if env_strategy == "symlink":
        target_env.symlink_to(source_env)
        print(f"linked .env: {target_env}")
        return

    if env_strategy == "copy":
        shutil.copy2(source_env, target_env)
        print(f"copied .env: {target_env}")
        return

    raise ManifestError("env_strategy must be 'symlink' or 'copy'")


def _state_path(plan: WorktreePlan) -> Path:
    return plan.worktrees_root / ".runs" / "worktree_tasks_state.json"


def _load_state(state_path: Path) -> dict[str, Any]:
    if not state_path.exists():
        return {"tasks": {}}
    loaded = json.loads(state_path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise ManifestError(f"Invalid state file: {state_path}")
    loaded.setdefault("tasks", {})
    return loaded


def _save_state(state_path: Path, state: dict[str, Any]) -> None:
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _record_status(state: dict[str, Any], task: WorktreeTask, *, status: str) -> None:
    tasks_state = state.setdefault("tasks", {})
    tasks_state[task.feature_id] = {
        "status": status,
        "branch": task.branch,
        "worktree_path": str(task.worktree_path),
        "work_item": task.work_item.as_posix(),
    }


def _print_status(plan: WorktreePlan) -> None:
    state = _load_state(_state_path(plan))
    tasks_state = state.get("tasks", {})
    for task in plan.execution_order:
        task_state = tasks_state.get(task.feature_id, {})
        status = task_state.get("status", "planned")
        print(f"{task.feature_id} {status} {task.branch} worktree={task.worktree_path}")


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
