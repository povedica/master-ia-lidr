# Spec: Pytest heavy-test opt-in (`slow` marker)

## Objective

Keep the default `uv run pytest` suite fast and offline-friendly by **deselecting** tests marked `slow`. Heavy tests (eval soft/judge multi-run, live LLM smoke) run only when explicitly opted in via `--run-heavy`, `-m slow`, or `RUN_HEAVY_TESTS=1`.

## Context

- The repo already defined a `slow` pytest marker (`pyproject.toml`) for eval soft/judge suites.
- Default `pytest` still collected those tests; with `EVAL_ESTIMATOR_USE_REAL_LLM=true` and judge credentials in the environment, a routine run took ~3 minutes and consumed API tokens.
- Session live smoke (`test_estimate_submit_live_llm_smoke`) was not marked `slow` and could run when `SESSION_INTEGRATION_TEST_USE_REAL_LLM=true`.

## Contract

### Marker

- **`slow`**: expensive or multi-run tests that may call real LLM providers or run many HTTP replays.
- Register in `[tool.pytest.ini_options].markers` (`pyproject.toml`).

### Default collection

- `uv run pytest` **deselects** all items with the `slow` marker (via `pytest_collection_modifyitems` in `tests/conftest.py`).
- Fast suite target: unit + mocked integration + hard evals (~400 tests, single-digit seconds).

### Opt-in (run heavy tests)

| Mechanism | Example |
|-----------|---------|
| CLI flag | `uv run pytest --run-heavy` |
| Env var | `RUN_HEAVY_TESTS=1 uv run pytest` |
| Marker expression | `uv run pytest -m slow` (includes heavy without `--run-heavy`) |
| Combined | `uv run pytest --run-heavy -m "evals and slow"` |

### When to mark `slow`

Add `@pytest.mark.slow` when a test:

- Calls a real OpenAI/Anthropic/judge provider (not mocked).
- Runs multiple LLM passes (soft consistency, judge GEval).
- Is documented as optional smoke / costs tokens.

Do **not** mark unit tests, mocked integration tests, or hard deterministic evals (fake LLM).

### Agent / task discipline

- **`/start-task`**, **`/finish-task`**, and routine validation: use default `uv run pytest` (no `--run-heavy`).
- Document heavy verification separately when a task requires it.
- New heavy tests **must** carry `@pytest.mark.slow` and document opt-in commands in the task or eval doc.

## Scope

### Includes

- `tests/conftest.py` collection hook and `--run-heavy` option.
- `@pytest.mark.slow` on live LLM smoke test.
- `tests/test_pytest_heavy_selection.py` guard test.
- README, `docs/evals/session-estimation-evals.md`, `docs/technical/README.md`.
- `.cursor/rules/05-testing-standards.mdc` policy update.

### Excludes

- CI workflow files (none in repo yet).
- Changing skip semantics inside eval modules (`requires_live_estimator`, etc.) — those remain as secondary guards.

## Rules

1. Default `pytest` must not require API keys or incur token cost.
2. Heavy tests are never removed; they are deselected, not deleted.
3. `-m slow` always includes heavy tests even without `--run-heavy`.
4. Prefer `--run-heavy` in docs when showing eval soft/judge commands.

## Acceptance Criteria

- [x] AC-01: `uv run pytest` deselects all `slow` tests by default.
- [x] AC-02: `uv run pytest --run-heavy -m slow` collects and runs `slow` tests.
- [x] AC-03: `uv run pytest -m slow` runs `slow` tests without `--run-heavy`.
- [x] AC-04: `RUN_HEAVY_TESTS=1` behaves like `--run-heavy`.
- [x] AC-05: `test_estimate_submit_live_llm_smoke` is marked `slow`.
- [x] AC-06: README and eval docs describe default vs opt-in commands.
- [x] AC-07: Testing standards rule documents the policy for future tasks.

## Verification

- **Verified:** `uv run pytest tests/test_pytest_heavy_selection.py` — 1 passed, 1 deselected.
- **Verified:** `uv run pytest tests/test_pytest_heavy_selection.py --run-heavy` — 2 passed.
- **Verified:** `uv run pytest` — 406 passed, 11 skipped, 10 deselected (~7 s).
- **Not verified:** `--run-heavy` full suite with live credentials (optional, costs tokens).

## Documentation Plan

- README § Tests
- `docs/evals/session-estimation-evals.md`
- `docs/technical/README.md` §15
- `.cursor/rules/05-testing-standards.mdc`
- `.cursor/skills/validation-pass-fastapi/SKILL.md`

## Pull request

- PR: https://github.com/povedica/master-ia-lidr/pull/28 (merged via `/finish-task`)

## Repository commits (master-ia)

| SHA | Message |
|-----|---------|
| 682718d | feat(testing): deselect slow tests by default with --run-heavy opt-in |
