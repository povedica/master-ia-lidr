# start-task

## Purpose

Kick off development work in `master-ia` from an **existing working document**: feature, decision, session note, bug, improvement, experiment, or technical note. The agent must read that document in depth, turn it into operational context, review related rules and code, and **execute** (or hand off) work using a **strict baby-steps + TDD** loop.

This command is the `master-ia` adaptation of the **`a-currar` workflow** (document-driven phases, quality gates, per-step commits, RED → GREEN → REFACTOR). The **source of truth** is **not** Linear: it is the document the user passes as input and the associated Second Brain material.

## When to use

Use `/start-task` when:

- The user wants to start implementing an already documented feature.
- A decision or session note must become an executable work plan.
- Work continues on a task started in the Second Brain.
- You need context before editing code.
- You want **enforced** baby steps, verification, TDD where practical, and living documentation.

To create the document from scratch, use `/write-feature` or `/docs` first. To close pending changes, use `/commit-pending`.

## Command input

The user passes the document to start from:

```text
/start-task learnings/second-brain-master-ia/proyectos/estimador-cag/work-items/feature-configuracion-inicial-cag.md
```

They may also use a Cursor reference:

```text
/start-task @learnings/second-brain-master-ia/proyectos/estimador-cag/work-items/feature-configuracion-inicial-cag.md
```

For the **versioned documentation mirror** (when the vault symlink is missing), paths under `proyectos/<project>/docs/` are valid canonical inputs too.

## Critical rule: single source of truth

- The input document is the **canonical** document for the task.
- Do not create another document for the same feature unless the user asks.
- All progress, plan changes, acceptance updates, commit log entries, and **learnings during implementation** go into **that same file** (or an explicitly linked note referenced from it).
- If the document is missing, empty, or unclear on goals, stop and ask. Suggest a likely path under `learnings/second-brain-master-ia/proyectos/<project>/work-items/` (or the versioned mirror under `docs/work-items/` in this repo).
- If session or project is unclear, infer from the path, suggest a default, and confirm before implementing.

---

## Workflow overview (aligned with `a-currar`, adapted to `master-ia`)

```text
Phase 0: Task intake      → Canonical doc, readiness, conflicts / WIP awareness
Phase 1: Standards        → Read relevant `.cursor/rules/`
Phase 2: Documentation    → Validate or complete canonical sections (still one file)
Phase 3: Planning         → Baby steps, dependencies, sizing, verification map
Phase 4: Setup            → Git branch policy, uv sync, subproject cwd if needed
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
3. Prefer **≤ ~100 meaningful changed lines per commit** where practical (same intent as `a-currar`); splitting deps / code / docs across commits is encouraged.
4. **Documentation must not lag more than one step** behind behavior changes (canonical document updated in the same step or immediate follow-up micro-commit).

If any hard-stop item is missing, **stop and ask** before touching application code.

---

## Phase 0. Task intake and canonical document

### 0.1 Read the input document

Extract:

- Primary objective.
- Task type: `feature`, `bug`, `refactor`, `docs`, `experiment`, `setup`, or `learning`.
- Affected project (e.g. `estimador-cag`, monorepo root `app/`).
- Linked session, if any.
- Included and excluded scope.
- Acceptance criteria.
- Existing implementation plan.
- Test or verification plan.
- External dependencies, LLM models, APIs, or environment variables.

### 0.2 Validate readiness (documentation gate)

Same checks as historical `start-task`, strengthened:

- [ ] Objective and scope are clear.
- [ ] Acceptance criteria exist or can be derived.
- [ ] **Test / verification strategy** exists (automated **or** explicit manual checklist).
- [ ] **Repository commits section** exists or you add `## Repository commits (master-ia)` (**table body in English**).
- [ ] No real secrets.
- [ ] Does not contradict repo rules.

If critical sections are missing, **pause implementation** and either complete the document (when intent is obvious) or route to `/write-feature`, `/requirement-validate`, etc., per complexity.

### 0.3 WIP awareness (Linear-free equivalent of “In Progress”)

Run or review:

```bash
git status
git status --short
git diff --stat
```

If there is **large unrelated dirt** or **mixed tasks** in one working tree, **warn the user** and agree what belongs to this canonical document before proceeding (same *focus discipline* as resolving multiple Linear “In Progress” issues).

### 0.4 Record destinations

- **Progress**: canonical input document (including an **Implementation progress** subsection if useful — see Phase 5.3).
- **Commits**: `## Repository commits (master-ia)` (or Spanish header if legacy, descriptions **English**).
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

### 2.2 Detect workflow flavor

- `feature`: new behavior — default **TDD** for logic.
- `bug`: reproduce → failing test → minimal fix.
- `refactor`: preserve behavior; characterization tests when risk warrants.
- `docs` / `setup` / `experiment` / `learning`: TDD only when it still reduces risk; **state the exception** under hard stop.

---

## Phase 3. Baby-steps planning

Build a plan. Each step uses this shape (same structure as `a-currar` Phase 3, adapted):

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

- `XS` | `S` | `M` | `L` | `XL` — same meaning as `a-currar`.
- `L` / `XL`: split into multiple documents or child tasks before coding.

### Optional external tracking

If the user uses Linear or another tracker, **they** update it; `start-task` does **not** require MCP or issue IDs.

---

## Phase 4. Environment and Git setup

### 4.1 Branch and PR policy (`a-currar` adapted)

- **Default (`master-ia`)**: do **not** open a PR or create a branch **unless the user asks** (project convention).
- **If the user requests a branch / PR** (optional `a-currar`-style flow):
  - Create `feature/…`, `fix/…`, or `chore/…` from up-to-date `main`.
  - Optionally open a **draft** PR early for traceability; link it in the canonical document.

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

## Phase 5. Implementation — TDD + baby steps (`a-currar` core)

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

- Prefer **one commit per plan step** (or tight pair: `test:` then `feat:` only when strictly needed for reviewer clarity).
- Commit messages **English**, conventional prefixes (`feat`, `fix`, `test`, `docs`, `chore`, `refactor`).

### 5.2 Push rhythm

If using a remote branch, push periodically (e.g. every few commits).

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
- [ ] Ready for **`/commit-pending`** grouping if the user wants multiple commits spelled out.

Optional: mark draft PR ready, self-review checklist (adapted from `a-currar`): criteria met, no stray debug prints, docs complete.

---

## Phase 7. Retrospective and learnings (`a-currar` adapted)

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

---

## Common scenarios (from `a-currar`, adapted)

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

- Before: `/write-feature` or `/requirement-write`; `/requirement-validate` when vague.
- Non-trivial: `/requirement-design`, `/requirement-tasks`.
- During: `/docs`, `/testing`, `/check-quality`, `/check-architecture`, `/check-dod`.
- After: `/commit-pending`.
- Learning-first: `/master-tutor`.

---

## Success criteria

`/start-task` succeeds when:

- The input document is the **single** canonical source.
- Hard-stop items (plan, per-step verification, **TDD or justified exception**) are satisfied **before** code.
- Phases **0–7** are applied at a proportionate weight (XS tasks may collapse phases lightly, but never skip explicit verification).
- Coding does not regress into “big bang” batches for testable logic.
- Documentation and commit-log destinations remain clear throughout.

---

## Changelog

- **2026-05-06**: Integrated **`a-currar`**-style phased flow and **strict** TDD + baby-steps commit cadence for `master-ia`; Phase 0 WIP replaces Linear intake; tooling mapped to **`uv`** / **`pytest`** / Second Brain paths; strengthened hard stop and documentation lag rule.

---

**Last updated:** 2026-05-06  
**Status:** Active
