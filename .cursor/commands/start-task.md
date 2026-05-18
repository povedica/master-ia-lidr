# start-task

## Purpose

Kick off feature development in `master-ia` from an **existing feature work item** under `docs/work-items/`. The agent must read that document in depth, validate that it is implementation-ready, open the task branch and WIP draft PR before production code, and execute work using a strict baby-steps + TDD loop.

The **source of truth** is the repository work-item document the user passes as input. Linear is not part of this workflow.

## When to use

Use `/start-task` when:

- The user wants to start implementing an already documented **feature**.
- The feature work item already exists as `docs/work-items/feature-NNN-<slug>.md`.
- You need enforced documentation readiness, baby steps, verification, TDD where practical, WIP PR tracking, and living documentation.

Do **not** use `/start-task` for bug fixes, improvements, specs, experiments, ADRs, or legacy feature filenames without `NNN`. Route those to the appropriate command instead. To create the feature document from scratch, use `/write-feature` first. To close pending changes, use `/commit-pending` or `/finish-task`.

## Command input

The user passes the full repository path to the feature document:

```text
/start-task docs/work-items/feature-016-unified-jinja2-prompt-templates-v2.md
```

They may also use a Cursor reference:

```text
/start-task @docs/work-items/feature-016-unified-jinja2-prompt-templates-v2.md
```

If the user gives only a feature name, `NNN`, or a description, ask for the exact `docs/work-items/feature-NNN-<slug>.md` path before proceeding.

## Critical rule: single source of truth

- The input document is the **canonical** document for the feature.
- The file path must be under `docs/work-items/` and the filename must match `feature-NNN-<kebab-slug>.md`.
- Do not create another document for the same feature.
- All progress, plan changes, acceptance updates, verification updates, PR links, and implementation learnings go into **that same file**.
- `## Repository commits (master-ia)` is added or updated during task closure, not during intake.
- If the document is missing, empty, legacy-named, or incomplete for the strict documentation gate, stop. Do not complete it inline during `/start-task`.

---

## Workflow overview

```text
Phase 0: Feature intake   → Canonical doc, strict readiness, same-feature WIP checks
Phase 1: Standards        → Read relevant `.cursor/rules/`
Phase 2: Documentation    → Validate canonical sections; stop if incomplete
Phase 3: Planning         → Baby steps, dependencies, sizing, `## Estimation`, verification map
Phase 4: Setup            → Branch, push, WIP draft PR + label before code
Phase 5: Implementation   → Strict TDD + baby steps + commit cadence + doc sync
Phase 6: Completion       → Final verification, doc accuracy, `/commit-pending` prep
Phase 7: Retrospective    → Learnings → canonical doc / aprendizajes / rules candidates
```

---

## Hard stop before coding

Before any implementation, the agent must complete and present in the chat:

- **Baby-steps plan** with **3–8 steps** (each step ideally one reviewer-friendly commit).
- For **every step that changes behavior**: **explicit TDD intent** — `RED → GREEN → REFACTOR`, including **which test file** will fail first and **which command** proves RED — **or** a one-line **justified exception** (e.g. “Streamlit layout only; manual smoke + screenshot checklist”) **before** writing production code.
- **Verification strategy per step** (command or manual check).
- **Open risks** and decisions that could change scope.

**Discipline (non-negotiable when TDD applies):**

1. For new or changed **logic** (pure functions, parsing, validation, error mapping, service contracts): add or extend a **failing test first**, run the narrowest `pytest` invocation to show **RED**, then implement **GREEN**, then **REFACTOR** only if it clarifies without scope creep.
2. **Do not** land production code and tests in one undifferentiated batch without having shown test-first order in the session (unless the justified exception applies).
3. Prefer **≤ ~100 meaningful changed lines per commit** where practical; splitting deps / code / docs across commits is encouraged.
4. **Documentation must not lag more than one step** behind behavior changes (canonical document updated in the same step or immediate follow-up micro-commit).
5. **Commit each completed baby step** once verification for that step is green (see Phase 5.F). Do **not** wait for a separate user message such as “commit” or “commitea” — `/start-task` implementation includes commits by default.

If any hard-stop item is missing, **stop and ask** before touching application code.

---

## Phase 0. Feature intake and canonical document

### 0.0 Validate input path and filename

Hard requirements:

- Path is under `docs/work-items/`.
- Filename matches `feature-NNN-<kebab-slug>.md`.
- The task is a feature. If the path points to `bugfix-*`, `spec-*`, `exp-*`, `adr-*`, an improvement, or any legacy feature filename without `NNN`, reject it and redirect to the appropriate command.

Derive:

- Feature ID: `NNN`.
- Slug: `<kebab-slug>`.
- Branch: `feature/NNN-<kebab-slug>`.

### 0.1 Read the input document

Extract:

- Primary objective.
- Task type: must be `feature`.
- Affected project (e.g. `estimador-cag`, monorepo root `app/`).
- Linked session, if any.
- Included and excluded scope.
- Acceptance criteria.
- Existing implementation plan.
- Test or verification plan.
- External dependencies, LLM models, APIs, or environment variables.

### 0.2 Validate readiness (documentation gate)

Strict checklist. Do not proceed to Phase 1 unless every required section is present and specific enough to implement:

- [ ] `## Objective`
- [ ] `## Context`
- [ ] `## Scope` with `### Includes` and `### Excludes`
- [ ] `## Functional Requirements` with concrete behavior and examples where useful
- [ ] `## Technical Approach`
- [ ] `## Acceptance Criteria` with testable criteria (target: about 10 or more for non-trivial features)
- [ ] `## Test Plan` with automated and/or manual coverage
- [ ] `## Verification` or an explicit verification subsection inside `## Test Plan`
- [ ] No real secrets.
- [ ] Does not contradict repo rules.

If the document is empty or incomplete, stop and tell the user exactly what is missing. Do not complete the document inline during `/start-task`; use `/write-feature` or an explicit document-editing request first.

### 0.3 Same-feature WIP check

Multiple features may be in progress at the same time. Block only when the same feature document appears to already have active work.

Check both signals:

```bash
git branch --list "feature/NNN-<kebab-slug>"
git branch -r --list "origin/feature/NNN-<kebab-slug>"
gh pr list --state open --search "docs/work-items/feature-NNN-<kebab-slug>.md"
```

Same-feature WIP exists if either:

- A local or remote branch named `feature/NNN-<kebab-slug>` already exists.
- An open PR title/body links the same `docs/work-items/feature-NNN-<kebab-slug>.md`.

If same-feature WIP exists, warn the user and stop. Do not auto-resume or replan inside `/start-task`; the user should decide the next step.

### 0.4 Working tree awareness

Run or review:

```bash
git status
git status --short
git diff --stat
```

If there is large unrelated dirt or mixed tasks in one working tree, warn the user and agree what belongs to this canonical document before proceeding.

### 0.5 Record destinations

- **Progress**: canonical input document (including an **Implementation progress** subsection if useful — see Phase 5.3).
- **Commits**: `## Repository commits (master-ia)` is written during completion as an implementation report with English summaries.
- **Sessions / learnings**: `learnings/second-brain-master-ia/proyectos/<project>/sesiones/` and `…/aprendizajes/` when applicable.

---

## Phase 1. Project standards

Read only what the task needs:

- Always: `.cursor/rules/00-base-standards.mdc`
- Baby steps discipline: `.cursor/rules/13-babysteps-principle.mdc`
- Python: `.cursor/rules/01-python-standards.mdc`
- FastAPI: `.cursor/rules/02-fastapi-standards.mdc` (when relevant)
- AI/LLM: `.cursor/rules/03-ai-engineering-standards.mdc` (when relevant)
- Environment and secrets: `.cursor/rules/04-environment-and-secrets.mdc`
- Tests: `.cursor/rules/05-testing-standards.mdc`
- Errors/logging: `.cursor/rules/06-error-handling-and-logging.mdc`
- Pre-implementation analysis: `.cursor/rules/07-pre-implementation-analysis.mdc`
- Refactoring: `.cursor/rules/08-refactoring-standards.mdc`

**Do not assume** Laravel, Sail, Pint, Pest, Composer, or Linear. This repo uses **Python**, **`uv`**, **`pytest`**, FastAPI when relevant, and Second Brain notes.

---

## Phase 2. Analysis and context

### 2.1 Find similar patterns

Depending on task type, review:

- Python at the repository root (`app/`, `tests/`), `learnings/notebooks/`, or paths implied by the document.
- Subproject layout: some packages live under `proyectos/<name>/` with their own `pyproject.toml` — run `uv` and `pytest` **from the correct directory**.
- `.env.example` when configuration is involved.
- Existing tests and routers/services boundaries.

### 2.2 Confirm feature workflow

`/start-task` only runs feature workflow. New or changed logic defaults to TDD. Documentation-only or setup-only slices still need a justified testing exception plus explicit verification.

---

## Phase 3. Baby-steps planning

Build a plan. Each step uses this shape:

```markdown
### Step N: [name]

**Goal**: …
**Changes**: files / modules
**TDD**: RED test name + path (or **Exception**: …)
**Verification**: `uv run pytest …` and/or manual
**Documentation**: bullet for canonical doc
**Suggested commit**: `type(scope): message`
```

### Plan criteria

- **5–30 minutes** per step when possible; **one focus** per step.
- Where behavior changes, **each step should end with tests passing** for that slice.
- Split **dependencies**, **production code**, **tests**, and **docs** across commits when size grows.
- Do not invent commands; use what exists (`uv run pytest`, `uv sync`, project README).

### Sizing (T-shirt)

- `XS` | `S` | `M` | `L` | `XL`.
- `L` / `XL`: split into multiple documents or child tasks before coding.

### Estimation section

After planning, update the canonical work item with:

```markdown
## Estimation

- Size: M
- Estimated time: 3 hours
- Planned steps: 6
```

External trackers are out of scope for `/start-task`.

---

## Phase 4. Environment and Git setup

### 4.1 Branch name, single branch until close, and WIP PR policy (`master-ia`)

**Canonical branch name (mandatory):**

Derive the git branch from the **work item filename**:

| Feature filename | Branch |
|------------------|--------|
| `docs/work-items/feature-014-remove-v2-estimate-stream-route.md` | `feature/014-remove-v2-estimate-stream-route` |

Create this branch from up-to-date **`main`** after Phase 0–3 are satisfied and **before any production code change**.

**One branch, one doc, until closure:**

- All implementation, tests, and completion reporting for this work item stay on **this branch** and in the same canonical file until the PR is merged or the user explicitly abandons the item.
- Do not route commits or progress for this feature into another `feature-NNN-*.md` document.

**Mandatory WIP draft PR before code:**

```bash
git checkout main
git pull origin main
git checkout -b feature/NNN-<kebab-slug>
git push -u origin feature/NNN-<kebab-slug>
gh pr create --draft --title "[WIP] feat: <short title>" --body "$(cat <<'EOF'
## Summary
- Implements `docs/work-items/feature-NNN-<kebab-slug>.md`.

## Status
- WIP draft PR. Implementation will proceed in baby steps.

## Test plan
- Planned verification is documented in the work item.
EOF
)"
gh label create wip --color F9D0C4 --description "Work in progress" || true
gh pr edit --add-label wip
```

Record the PR URL in the canonical work item.

**Exceptions:**

- **Local-only**: only skip branching, push, or PR when the user **explicitly** asks (spike, no remote). State what was skipped in chat and the canonical doc.
- **WIP hygiene**: do not open a PR that bundles **unrelated** dirty work; resolve mixed-task trees in Phase 0 first.

Follow the repository’s PR workflow (title/body, test plan): use `gh` from a clean, task-scoped branch.

### 4.2 Python / uv

From the **relevant** project root (monorepo root vs `proyectos/<pkg>/`):

```bash
uv sync
# When dev groups exist:
uv sync --group dev
```

Dependencies: **`uv add <pkg>`** in that project; update `.env.example` and README when behavior or config changes.

### 4.3 Secrets

Never commit `.env`. No keys in prompts, tests, logs, or mirrored docs.

---

## Phase 5. Implementation — TDD + baby steps

Execute **one plan step at a time**. For each step that includes testable logic:

### A. RED — failing test first

- Add or extend the smallest failing test (`pytest`, Arrange-Act-Assert).
- Run the **narrowest** command, e.g.:

```bash
<project-root>
uv run pytest tests/test_module.py::test_name -q
```

- Confirm failure for the **right reason** (assertion / expected error), not import noise.

### B. GREEN — minimal implementation

- Write the smallest change to pass the test.
- Re-run the same narrow command, then broaden if needed:

```bash
uv run pytest tests/test_module.py -q
uv run pytest
```

### C. REFACTOR

- Improve clarity only; **keep tests green**. No drive-by scope.

### D. Quality checks

- Prefer full suite **`uv run pytest`** before declaring the step done.
- Use **`read_lints`** (or project linter config if documented) when editing non-trivial Python.

### E. Living documentation (**before or with** the commit)

Update the canonical document when acceptance criteria, APIs, env vars, or verification change. **Never** let the doc drift more than **one step**.

### F. Commit (baby-step cadence)

After each plan step is **verified** (tests green or documented manual check), create a **safe-to-commit** increment:

- **One commit per completed baby step** when the tree is green for that slice (or a tight pair: `test:` then `feat:` only when reviewers need the split).
- **Do not batch** multiple plan steps into one commit unless they are mechanically inseparable (call that out in the commit message).
- **Do not pause** implementation with a large staged diff waiting for the user to ask for commits — committing is part of `/start-task`, not a separate optional phase.
- Skip a commit only when the step left nothing committable (e.g. planning-only chat) or when files must not land yet (secrets, broken tests); say so explicitly before moving on.
- Commit messages **English**, conventional prefixes (`feat`, `fix`, `test`, `docs`, `chore`, `refactor`).
- Append a row to **`## Repository commits (master-ia)`** in the canonical work item when that section exists or as soon as implementation starts recording commits.

### 5.2 Push rhythm

Push the task branch to the remote **periodically** (e.g. every few commits) and before updating the PR, so review and CI see the latest commits.

### 5.3 Progress checklist in the canonical doc

Maintain a lightweight block (when useful):

```markdown
## Implementation progress

- [ ] Step 1: …
- [ ] Step 2: …
```

---

## Phase 6. Completion and commit preparation

- [ ] Full applicable **`uv run pytest`** for the touched project(s).
- [ ] Canonical document: acceptance criteria and **verification** match reality.
- [ ] **`git status`** clean or intentional; no secrets staged.
- [ ] **`## Repository commits (master-ia)`** table updated with **English** summaries.
- [ ] **Branch pushed** and **WIP draft PR opened** on the remote (unless the user explicitly opted out in Phase 4.1).
- [ ] Ready for **`/commit-pending`** grouping if the user wants multiple commits spelled out.

Optional: remove the `wip` label, mark the draft PR ready, and run a self-review checklist: criteria met, no stray debug prints, docs complete.

---

## Phase 7. Retrospective and learnings

Answer briefly:

1. **Process**: Was TDD honored? Were commits truly small?
2. **Technical**: Patterns reused correctly?
3. **Quality**: Edge cases covered?
4. **Docs**: Could someone else onboard from the canonical file alone?

**Outputs:**

- **Feature-specific**: canonical document (consider **Learnings** subsection — optional but encouraged for non-trivial work).
- **Reusable**: `learnings/second-brain-master-ia/proyectos/<project>/aprendizajes/` (Spanish allowed for reflective notes per project norms; paths and commands still English).
- **Rule candidates**: propose updates to `.cursor/rules/` **only** if broadly applicable and non-duplicative.

---

## Expected output immediately after `/start-task`

Before coding:

- Task summary, canonical path, task type.
- Standards actually read (list filenames).
- Relevant repo areas / subprojects.
- Risks and open decisions.
- **Numbered baby-steps plan** with **per-step TDD** or justified exception.
- Where progress and commits are recorded.

After **implementation** (when requested in the same invocation):

- Per-step adherence: RED shown (or exception logged), GREEN, commits implied or listed.
- Residual risks and **not verified** items stated explicitly.
- **Remote PR** link and WIP label status (or explicit note that the user opted out of branch/PR).

---

## Common scenarios

### Tests reveal bad design

Pause, revise the canonical document and plan, commit doc/plan adjustment, resume.

### External dependency needed

Ded vote in plan → `uv add` → lockfile → document in README / `.env.example` → dedicate a small commit.

### Scope creep

Small → extend plan and document; large → **`Out of scope` / Future work** item; avoid mixing unrelated fixes.

### Failing CI or `pytest`

Fix before moving on; do not advance the plan with a red suite.

---

## Integration with other commands

- Before: `/write-feature`; `/requirement-validate` when vague.
- Non-trivial: `/requirement-design`, `/requirement-tasks`.
- During: `/docs`, `/testing`, `/check-quality`, `/check-architecture`, `/check-dod`.
- After: `/commit-pending`.
- Learning-first: `/master-tutor`.

---

## Success criteria

`/start-task` succeeds when:

- The input document is the **single** canonical source.
- The input path is `docs/work-items/feature-NNN-<slug>.md`.
- The strict documentation gate passes before planning and code.
- Hard-stop items (plan, per-step verification, **TDD or justified exception**) are satisfied **before** code.
- Phases **0–7** are applied at a proportionate weight (XS tasks may collapse phases lightly, but never skip explicit verification).
- Coding does not regress into “big bang” batches for testable logic.
- Documentation and commit-log destinations remain clear throughout.
- Unless the user opted out, the work starts on a **pushed branch** with a **draft PR** carrying the `wip` label before production code.

---

## Changelog

- **2026-05-17 (b)**: Phase 5.F and hard-stop discipline: commit each verified baby step during `/start-task` without waiting for a separate user “commit” request.
- **2026-05-17**: Restricted `/start-task` to `docs/work-items/feature-NNN-<slug>.md`, added strict feature documentation gate, same-feature WIP blocking by branch or PR, mandatory draft PR with `wip` label before code, and `## Estimation` planning output.
- **2026-05-15 (b)**: **Canonical branch name** from work item filename (`feature/NNN-slug`); **one branch + one doc** until merge; forbid logging feature A commits in feature B’s table.
- **2026-05-15**: **Default branch + remote PR** for `start-task` (Phase 4.1, Phase 5.2, Phase 6, success criteria); explicit **opt-out** when the user requests local-only work; WIP hygiene for PR scope.

---

**Last updated:** 2026-05-17  
**Status:** Active
