# Feature: Parallel Worktree Task Orchestrator

## Objective

Build a small repository-local orchestration tool that prepares isolated Git worktrees for feature work items and, in a later optional layer, launches Cursor SDK agents against those worktrees with bounded parallelism.

The goal is to make feature parallelization repeatable and safe: each task gets its own worktree, canonical branch, environment bootstrap, instructions, and run status, while preserving the existing `/start-task` discipline for feature implementation.

## Context

The current `master-ia` workflow already has strong feature execution rules:

- `/start-task` derives canonical branches from `docs/work-items/feature-NNN-<slug>.md`, opens a draft PR, and commits verified baby steps.
- `/commit-pending` and `/finish-task` expect the same canonical document and branch to remain the source of truth.
- Feature epic `feature-041-retrieval-debug-observability-screen.md` already splits retrieval debugging into sub-features 042-048 with explicit dependencies and some parallelizable branches.

The missing piece is an automation layer that prepares and tracks multiple isolated worktrees without reimplementing `/start-task`.

Important repository constraints:

- `.env` is ignored and is not present in a new worktree unless explicitly linked or copied.
- Each worktree needs its own `.venv` through `uv sync --group dev`.
- Docker Compose exposes shared local services on fixed ports: Postgres `5432`, Redis `6379`, API `8000`, and web `5175`.
- Default tests should remain deterministic and should not require real API keys or live Postgres.
- Cursor SDK local runtime still consumes Cursor usage through `CURSOR_API_KEY`; without on-demand enabled, SDK runs may stop when included usage is exhausted.

## Scope

### Includes

- A Python CLI under `scripts/worktree_tasks.py` for:
  - validating a declarative task manifest,
  - planning dependency order,
  - preparing worktrees and canonical branches,
  - bootstrapping local environment files safely,
  - writing per-worktree manual instructions,
  - tracking task status and cleanup metadata.
- A sample manifest for the retrieval debug sub-features 042-048.
- A stdlib-only MVP for `plan`, `prepare`, `status`, and `cleanup`.
- Unit tests for manifest parsing, dependency validation, branch/path derivation, and safe command planning.
- Documentation explaining the workflow, safety limits, Cursor SDK quota caveat, and live database serialization policy.
- A documented extension point for future Cursor SDK execution with bounded `max_parallel`.

### Excludes

- Implementing the retrieval debug features themselves.
- Running multiple live Postgres or Redis instances per worktree in the MVP.
- Launching Docker Compose, Uvicorn, Vite, or live database verification automatically.
- Persisting or exporting Cursor agent transcripts beyond local run status metadata.
- Adding real secrets, API keys, or `.env` contents to Git.
- Replacing `/start-task`, `/commit-pending`, or `/finish-task`.

## Functional Requirements

### FR-01 - Manifest format

The tool must read a YAML manifest with defaults and task entries:

```yaml
defaults:
  worktrees_root: ../master-ia-worktrees
  base_branch: main
  max_parallel: 2
  env_strategy: symlink
tasks:
  - work_item: docs/work-items/feature-042-retrieval-debug-api-foundation.md
    depends_on: []
    needs_live_db: true
    mode: prepare
```

Task-level fields:

- `work_item`: required repository-relative path to a `docs/work-items/feature-NNN-<slug>.md` file.
- `depends_on`: optional list of feature IDs such as `042` or paths.
- `needs_live_db`: optional boolean, default `false`.
- `mode`: optional `prepare` or `sdk`, default `prepare`.
- `mutex_group`: optional string used to avoid launching tasks that are likely to edit the same files concurrently.

Derived fields:

- feature ID and slug from the work item filename,
- branch `feature/NNN-<slug>`,
- worktree path `<worktrees_root>/feature-NNN-<slug>`,
- default prompt `/start-task <work_item>`.

### FR-02 - Plan command

`python scripts/worktree_tasks.py plan -f <manifest>` must:

- validate all work item paths and filename patterns,
- validate dependencies and reject cycles,
- print or return the topological execution order,
- identify tasks currently blocked by dependencies,
- report derived branches and worktree paths,
- perform no filesystem or Git mutations.

### FR-03 - Prepare command

`python scripts/worktree_tasks.py prepare -f <manifest> [--only 049]` must:

- create a worktree outside the repository tree by default,
- create the canonical branch from the configured base branch,
- avoid recreating existing worktrees unless an explicit reuse flag is passed,
- create per-worktree `INSTRUCTIONS.md` with the manual Cursor command and SDK prompt,
- record status as `prepared`.

The command must not open PRs or run `/start-task` itself in the MVP. That remains manual or future SDK-runner behavior.

### FR-04 - Environment bootstrap

For each prepared worktree, the tool must support:

- `env_strategy: symlink` to symlink the repository root `.env` into the worktree when it exists,
- `env_strategy: copy` to copy `.env` only when explicitly requested,
- no-op with a clear warning when `.env` does not exist,
- `uv sync --group dev` as an optional bootstrap step controlled by a flag,
- `web/.env.local` preparation only when explicitly requested or documented for frontend work.

Secrets must never be printed, logged, or written to manifest/status files.

### FR-05 - Status tracking

The tool must persist local status metadata outside the repository tree by default, next to the worktrees:

- `planned`,
- `prepared`,
- `running`,
- `blocked`,
- `done`,
- `failed`,
- `failed_quota`,
- `manual_required`.

`status` must show task ID, branch, worktree path, dependency state, mode, and last error summary without secret values.

### FR-06 - Cleanup command

`cleanup` must:

- remove only selected worktrees,
- support a conservative `--merged-only` mode,
- run `git worktree prune` after removals,
- never delete unmerged or dirty worktrees unless an explicit force flag is used.

### FR-07 - Future SDK runner contract

The implementation must leave a clear extension point for a future `run` command that:

- requires `CURSOR_API_KEY` in the environment,
- uses bounded `max_parallel` with default `2`,
- maps quota/authentication errors to `failed_quota` or `manual_required`,
- respects `needs_live_db` serialization and `mutex_group`,
- falls back to manual execution instructions when SDK execution is unavailable.

## Technical Approach

- Use `scripts/worktree_tasks.py` as the CLI entrypoint because the functionality orchestrates repository workflow rather than FastAPI application behavior.
- Keep the MVP stdlib-only. Use `argparse`, `dataclasses`, `pathlib`, `json`, `subprocess`, and `graphlib.TopologicalSorter`.
- Parse YAML through PyYAML only if the existing dev dependency is available; otherwise support JSON for the MVP or add a small dependency deliberately through `uv add --dev pyyaml` if needed. The repository already lists `pyyaml` in the dev group, so the implementation may use it without adding a new package.
- Keep command execution behind small functions so pure planning logic can be unit tested without running Git.
- Store local run state under `<worktrees_root>/.runs/worktree_tasks_state.json`.
- Generate `INSTRUCTIONS.md` in each worktree with:
  - work item path,
  - branch name,
  - manual command `/start-task <work_item>`,
  - dependency notes,
  - live database warning when `needs_live_db=true`.
- Put the sample manifest under `docs/technical/worktree-task-orchestrator.example.yaml` or `scripts/worktree-tasks.example.yaml`.
- Document usage in `docs/technical/README.md` and add a short README pointer if useful.

## Acceptance Criteria

- [ ] AC-01: A valid manifest with feature work items produces deterministic derived IDs, slugs, branches, worktree paths, and prompts.
- [ ] AC-02: Invalid work item paths, legacy feature filenames, duplicate task IDs, missing dependencies, and dependency cycles fail with clear messages.
- [ ] AC-03: `plan` is read-only and produces an ordered dependency view without creating files, branches, or worktrees.
- [ ] AC-04: `prepare` creates one selected worktree outside the repository tree with the expected canonical branch.
- [ ] AC-05: Re-running `prepare` is idempotent and does not overwrite an existing worktree without an explicit reuse flag.
- [ ] AC-06: `prepare` writes `INSTRUCTIONS.md` with the correct `/start-task docs/work-items/feature-NNN-<slug>.md` command.
- [ ] AC-07: `.env` bootstrap uses symlink by default, warns when missing, and never logs secret values.
- [ ] AC-08: Optional `uv sync --group dev` bootstrap is available but not forced during pure planning.
- [ ] AC-09: `status` reports task state, branch, worktree path, and dependency status from persisted local metadata.
- [ ] AC-10: `cleanup --merged-only` refuses dirty or unmerged worktrees and prunes safe removals.
- [ ] AC-11: Documentation explains the Cursor SDK quota caveat and the fallback manual workflow.
- [ ] AC-12: Documentation explains that live Postgres/Redis verification is serialized in the MVP because Compose uses shared fixed ports.
- [ ] AC-13: Unit tests cover parsing, validation, topological ordering, branch derivation, path derivation, and command planning.
- [ ] AC-14: Default validation runs without real API keys and without live external provider calls.

## Test Plan

- Unit tests:
  - manifest parsing and defaults,
  - work item filename validation,
  - branch and worktree path derivation,
  - dependency graph sorting and cycle detection,
  - status model serialization,
  - command planning without invoking Git.
- Integration-style tests with temporary directories:
  - prepare command against a temporary Git repository when practical,
  - instructions file generation,
  - status file creation and update,
  - cleanup refusal for dirty worktrees.
- Manual checks:
  - run `plan` against the retrieval 042-048 sample manifest,
  - prepare one worktree and inspect `git worktree list`,
  - verify `INSTRUCTIONS.md` contains the expected `/start-task` command,
  - confirm no `.env` contents are printed.

## Verification

- Automated:
  - `uv run pytest tests/scripts/test_worktree_tasks.py -q`
  - `uv run pytest`
- Manual:
  - `python scripts/worktree_tasks.py plan -f docs/technical/worktree-task-orchestrator.example.yaml`
  - `python scripts/worktree_tasks.py prepare -f docs/technical/worktree-task-orchestrator.example.yaml --only 049 --dry-run`
  - `git worktree list`
- Not verified yet:
  - Real Cursor SDK execution.
  - Parallel live database verification.
  - Multiple Postgres/Redis instances per worktree.

## Documentation Plan

- Add usage instructions to `docs/technical/README.md`.
- Add or link a sample manifest for the retrieval debug features 042-048.
- Mention the workflow from `README.md` only if the tool becomes part of normal local development.
- Record that `.env` is linked/copied locally and never committed.
- Record SDK quota behavior: local Cursor SDK runs still consume Cursor usage and may stop without on-demand enabled.

## Implementation Plan

- [ ] Step 1: Add manifest models, filename validation, branch/path derivation, and graph validation with unit tests.
- [ ] Step 2: Add `plan` CLI command as a read-only dry-run.
- [ ] Step 3: Add `prepare` worktree command planning and implement safe worktree creation with tests around command construction.
- [ ] Step 4: Add environment bootstrap and `INSTRUCTIONS.md` generation.
- [ ] Step 5: Add persisted status plus `status` command.
- [ ] Step 6: Add conservative `cleanup` command.
- [ ] Step 7: Add sample manifest and technical documentation.
- [ ] Step 8: Add documented `run-sdk` extension point without fully launching agents unless explicitly split into a follow-up.

## Learnings

- Worktrees isolate tracked files and branches, but not ignored local files such as `.env` or `.venv`.
- Parallel code/test work is safer than parallel live-service verification because the repository's Compose file exposes shared fixed ports.
- A worktree inside the repository tree can confuse Cursor indexing and test discovery; a sibling directory is safer.
- Cursor SDK local runtime is not free local inference; it still consumes Cursor usage via `CURSOR_API_KEY`.

## Estimation

- Size: M
- Estimated time: 4-6 hours for MVP prepare/status/cleanup and docs.
- Planned steps: 8

## Implementation progress

- [x] Step 1: Manifest models and graph validation.
- [x] Step 2: Read-only plan command.
- [ ] Step 3: Safe prepare command.
- [ ] Step 4: Environment bootstrap and instructions.
- [ ] Step 5: Status command.
- [ ] Step 6: Cleanup command.
- [ ] Step 7: Sample manifest and docs.
- [ ] Step 8: SDK runner extension point.

### Step 1 verification

- RED: `uv run pytest tests/scripts/test_worktree_tasks.py -q` failed with `ModuleNotFoundError: No module named 'scripts.worktree_tasks'`.
- GREEN: `uv run pytest tests/scripts/test_worktree_tasks.py -q` passed (`5 passed`).

### Step 2 verification

- RED: `uv run pytest tests/scripts/test_worktree_tasks.py::test_plan_command_outputs_order_and_does_not_create_worktrees -q` failed because `main` was not yet implemented.
- GREEN: `uv run pytest tests/scripts/test_worktree_tasks.py -q` passed (`6 passed`).

## Repository commits (master-ia)

| Short hash | Message | Scope / summary |
|------------|---------|-----------------|
| `6cd355c` | `docs(worktree): add parallel task orchestrator work item` | Added the canonical feature document for the worktree orchestration task. |
| `b1d93a0` | `docs(worktree): record draft PR link` | Recorded the WIP draft PR link in the canonical work item. |
| `2d43551` | `feat(worktree): add manifest planning core` | Added manifest identity derivation, dependency graph validation, and first unit tests. |
| `ab7fca6` | `docs(worktree): record manifest core commit` | Added the repository commit table and recorded initial implementation traceability. |
| `334e3c4` | `feat(worktree): add manifest plan command` | Added the read-only manifest `plan` CLI command and YAML/JSON manifest loading. |

## Pull Request

- https://github.com/povedica/master-ia-lidr/pull/38
