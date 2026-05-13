# continue-task

## Purpose

Resume implementation work from an **existing canonical feature document** that was previously created with `/write-feature` and later refined with `/update-feature`, continuing from the **latest agreed state** instead of restarting intake.

## When to use

Use `/continue-task` when:

- The feature spec already exists and has been updated with new instructions.
- The task was started earlier and is now partially implemented, paused, or waiting for follow-up work.
- You want to keep the **same feature document** as the source of truth.
- You want to preserve baby steps, TDD, and doc sync without repeating the full first-pass intake.

Use `/start-task` when the work is being kicked off for the **first time** from a document, including non-feature work items.

## Command input

The user passes the canonical feature document to continue from:

```text
/continue-task learnings/second-brain-master-ia/proyectos/estimador-cag/work-items/feature-configuracion-inicial-cag.md
```

Or using a Cursor reference:

```text
/continue-task @learnings/second-brain-master-ia/proyectos/estimador-cag/work-items/feature-configuracion-inicial-cag.md
```

If the repository uses the **versioned documentation mirror**, paths under `proyectos/<project>/docs/` are also valid canonical inputs (see `.cursor/rules/11-spec-system.mdc`).

If the user gives only a feature name and more than one document could match, ask for the exact path before reading or editing anything.

## Critical rule: same source of truth

- The input document remains the **single canonical document** for the task.
- Do **not** create a new feature document, continuation note, or parallel task document unless the user explicitly asks.
- Record resumed progress, scope adjustments, acceptance updates, verification notes, implementation learnings, and repository commit entries in **that same file**.
- Treat the **latest version** of the document, including `/update-feature` edits, as the current truth.

---

## Workflow overview

```text
Phase 0: Resume intake    → Read canonical doc, inspect progress, detect unfinished work
Phase 1: Standards        → Re-read only the rules relevant to the resumed scope
Phase 2: Current state    → Compare spec, codebase, tests, and git state
Phase 3: Resume planning  → Define the next baby steps from the current point
Phase 4: Implementation   → Continue with strict TDD + verification + doc sync
Phase 5: Completion       → Reconcile progress, acceptance criteria, verification, and commit prep
```

Phases **4–5** follow the same **non-negotiable** discipline as `/start-task`:
RED → GREEN → REFACTOR where applicable, living docs, and small commits. When in doubt, apply the detailed implementation steps in `/start-task`.

---

## Phase 0: Resume intake

1. Read the canonical document end to end, especially Objective, Scope, Acceptance criteria, Test plan, Technical approach, and any **Implementation progress** or **Repository commits** sections.
2. Infer what is done, in progress, or not started, and note any mismatch between the document and reality.
3. Run `git status` and `git diff --stat` for WIP awareness; warn if unrelated dirt or mixed tasks could blur scope.
4. If the document is missing critical acceptance or verification for the *remaining* work, pause and either update the spec with user consent or route to `/requirement-validate` or `/write-feature` as appropriate.

---

## Phase 1: Standards (scoped)

Re-read only what the **remaining** work needs, for example:

- Always: `.cursor/rules/00-base-standards.mdc`, `.cursor/rules/13-babysteps-principle.mdc`
- API: `.cursor/rules/02-fastapi-standards.mdc`
- LLM: `.cursor/rules/03-ai-engineering-standards.mdc`
- Config: `.cursor/rules/04-environment-and-secrets.mdc`
- Tests: `.cursor/rules/05-testing-standards.mdc`
- Spec location / naming: `.cursor/rules/11-spec-system.mdc`

Do not re-read the entire ruleset by default.

---

## Phase 2: Current state

1. Spec vs code: locate touched modules, routers, services, and settings; confirm behavior matches the latest spec text.
2. Tests: identify existing coverage for the remaining slice and note gaps.
3. Git: relate the current branch and commits to the canonical **Repository commits** table; avoid duplicating or contradicting recorded work.

---

## Phase 3: Resume planning

Before writing production code, present a short plan in chat:

- **3–8 baby steps** from the current point, not from zero.
- For every step that changes behavior: **TDD intent** (`RED → GREEN → REFACTOR`), including which test file and which `pytest` command shows RED, or a one-line justified exception.
- **Verification** per step (`uv run pytest …`, manual check, or both).
- **Open risks** and decisions that could change scope.

Update the canonical doc’s **Implementation progress** or equivalent if the plan shifts.

---

## Phase 4: Implementation

Execute **one plan step at a time**:

- RED → GREEN → REFACTOR for testable logic; narrow `pytest` first, then broaden.
- Keep **documentation lag <= one step**. Update acceptance, verification, env vars, and API notes in the same canonical file when behavior changes.
- Prefer **English** commit messages and small, focused commits.
- Run `uv` and `pytest` from the **correct project root** when work lives under `proyectos/<pkg>/`.

---

## Phase 5: Completion

- Reconcile **acceptance criteria** and **verification** with what was actually done.
- Update **`## Repository commits (master-ia)`** with English summaries.
- State explicitly: **Verified**, **Not verified**, **Residual risk**.
- If the user wants commits grouped or finalized, point to `/commit-pending`; for full closure and optional PR flow, point to `/finish-task`.

---

## Integration with other commands

- Before: `/write-feature`, `/update-feature`; `/requirement-validate` or `/requirement-design` if scope is still fuzzy.
- First-time execution from a doc: `/start-task` (broader intake).
- Resume or delta work on the same feature file: `/continue-task` (this command).
- During: `/testing`, `/check-quality`, `/check-architecture`, `/check-dod`; skill `validation-pass-fastapi` when applicable.
- After: `/commit-pending`, `/finish-task`.

---

## Success criteria

`/continue-task` succeeds when:

- The **same** canonical document remains the only spec source; no parallel feature file is created.
- Remaining work is grounded in the latest post-`/update-feature` state.
- A clear **resume plan** and **per-step verification** exist before new production code.
- Progress, commits, and verification evidence are reflected in that one file, with an honest **Verified / Not verified / Residual risk** summary at the end of the session.

---

**Last updated:** 2026-05-13  
**Status:** Active
