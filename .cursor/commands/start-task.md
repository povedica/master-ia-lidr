# start-task

## Purpose

Kick off development work in `master-ia` from an **existing working document**: feature, decision, session note, bug, improvement, experiment, or technical note. The agent must read that document in depth, turn it into operational context, review related rules and code, propose a baby-steps plan, and make explicit what will be implemented, how it will be verified, and where progress will be recorded.

This command mirrors the full `a-currar` style workflow, adapted to `master-ia`: the source of truth is not Linear, but the document the user passes as input and the associated Second Brain material.

## When to use

Use `/start-task` when:

- The user wants to start implementing an already documented feature.
- A decision or session note must become an executable work plan.
- Work continues on a task started in the Second Brain.
- You need context before editing code.
- You want baby steps, verification, and living documentation.

To create the document from scratch, use `/write-feature` or `/docs` first. To close pending changes, use `/commit-pending`.

## Command input

The user passes the document to start from:

```text
/start-task second-brain-master-ia/proyectos/estimador-cag/decisiones/feature-configuracion-inicial-cag.md
```

They may also use a Cursor reference:

```text
/start-task @second-brain-master-ia/proyectos/estimador-cag/decisiones/feature-configuracion-inicial-cag.md
```

## Critical rule: single source of truth

- The input document is the **canonical** document for the task.
- Do not create another document for the same feature unless the user asks.
- Decisions discovered during analysis go back into the same document or into an explicitly linked note.
- If the document is missing, empty, or unclear on goals, stop and ask. Always suggest a likely path under `second-brain-master-ia/proyectos/<project>/decisiones/`.
- If session or project is unclear, infer from the path, suggest a default, and confirm before implementing.

## Workflow overview

```text
Phase 0: Document     -> Read input, validate canonical source, detect task type
Phase 1: Standards     -> Read relevant `.cursor/rules/`
Phase 2: Context       -> Inspect repo, notes, and similar patterns
Phase 3: Planning      -> Baby-steps plan, risks, verification
Phase 4: Setup         -> Git, dependencies, environment
Phase 5: Implementation-> Small steps, tests, living documentation
Phase 6: Completion    -> Validate, update docs, prepare `/commit-pending`
Phase 7: Learnings     -> Extract reusable learnings when applicable
```

---

## Phase 0. Working document

### 0.1 Read the input document

Read the full file or the relevant sections if it is long. Extract:

- Primary objective.
- Task type: `feature`, `bug`, `refactor`, `docs`, `experiment`, `setup`, or `learning`.
- Affected project, e.g. `estimador-cag`.
- Linked session, if any.
- Included and excluded scope.
- Acceptance criteria.
- Existing implementation plan.
- Test or verification plan.
- External dependencies, LLM models, APIs, or environment variables.

### 0.2 Validate that the document is ready to start

Before editing code, check:

- [ ] The objective is clear.
- [ ] Scope is bounded.
- [ ] Acceptance criteria exist or can be derived.
- [ ] The document states where to record progress and commits (or you add that in English).
- [ ] It contains no real secrets.
- [ ] It does not contradict repo rules.

If something important is missing, complete the document when intent is obvious. Otherwise ask the user with a concrete suggestion.

### 0.3 Identify documentation and commit destinations

Defaults:

- Progress and decisions: the input document.
- Commits: section `## Commits del repositorio (master-ia)` (or `## Repository commits (master-ia)`) in that same document; **table body in English** per base standards.
- Session: note under `second-brain-master-ia/proyectos/<project>/sesiones/` when applicable.
- Reusable learnings: `second-brain-master-ia/proyectos/<project>/aprendizajes/`.

Follow `/commit-pending` for workflow; if the commit log destination is unclear, ask before committing and suggest a path.

---

## Phase 1. Project standards

Read only the rules needed for the task:

- Always: `.cursor/rules/00-base-standards.mdc`
- Python: `.cursor/rules/01-python-standards.mdc`
- FastAPI: `.cursor/rules/02-fastapi-standards.mdc`
- AI/LLM: `.cursor/rules/03-ai-engineering-standards.mdc`
- Environment and secrets: `.cursor/rules/04-environment-and-secrets.mdc`
- Tests: `.cursor/rules/05-testing-standards.mdc`
- Errors/logging: `.cursor/rules/06-error-handling-and-logging.mdc`
- Pre-implementation analysis: `.cursor/rules/07-pre-implementation-analysis.mdc`
- Refactoring: `.cursor/rules/08-refactoring-standards.mdc`

Do not assume Laravel, Sail, Pint, Pest, or Linear. This repo uses Python, `uv`, notebooks, FastAPI when relevant, and Second Brain notes.

---

## Phase 2. Analysis and context

### 2.1 Inspect repository state

Run or review:

```bash
git status
git status --short
git diff --stat
```

Identify:

- Pending user changes.
- Files already modified that you must not overwrite.
- Current branch and relation to `origin`.
- Whether separate commits will be needed later.

### 2.2 Find similar patterns

Depending on task type, review:

- Existing Python under `proyectos/`, `app/`, `notebooks/`, or paths implied by the document.
- `pyproject.toml` for dependencies and available commands.
- `.env.example` when configuration is involved.
- Existing tests, if any.
- Related notes under `second-brain-master-ia/`.

Do not implement until local patterns are understood or you confirm the project is still initial scaffold.

### 2.3 Detect workflow flavor

From the document and context:

- `feature`: new behavior.
- `bug`: reproduce, isolate root cause, minimal fix.
- `refactor`: preserve behavior; add characterization tests when risk warrants.
- `docs`: sync README, commands, rules, or Second Brain technical content.
- `setup`: structure, dependencies, configuration, minimal verification.
- `experiment`: isolate hypothesis, record results, avoid mixing into production shape.
- `learning`: explain, practice, document takeaways.

---

## Phase 3. Baby-steps planning

Build a short, executable plan. Each step should use this shape:

```markdown
### Step N: [name]

**Goal**: what this unblocks.
**Changes**: expected files or modules.
**Verification**: test, command, or manual check.
**Documentation**: what updates in the canonical document.
**Suggested commit**: `type(scope): message`
```

### Plan criteria

- Steps of about 10–30 minutes when possible.
- One focus per step.
- Tests or checks proportional to risk.
- Split config, code, tests, and docs when they grow too large.
- Do not invent validation commands that do not exist in the repo.

### Estimate complexity

Classify:

- `XS`: small change, docs, or tiny tweak.
- `S`: scaffold or small feature.
- `M`: several pieces with tests and configuration.
- `L`: should be split into subtasks.
- `XL`: propose multiple features or documents.

If the plan is `L` or `XL`, suggest splitting before implementing.

---

## Phase 4. Environment setup

### 4.1 Git

Before editing:

- Check `git status`.
- Do not revert unrelated user work.
- If unrelated changes exist, work around them.
- If the user wants a branch or PR, create the branch before touching code.

In `master-ia`, do not open a PR automatically unless explicitly requested. The usual flow may be direct work on `main` with small commits traced in the Second Brain.

### 4.2 Python environment

When the task touches Python or dependencies:

```bash
uv sync
```

If you add a dependency, use the project package manager and update documentation.

### 4.3 Configuration and secrets

- Never create or commit a real `.env`.
- Update `.env.example` when introducing a new variable.
- Document variables in the README or canonical document.
- Never put real keys in prompts, tests, logs, or notes.

---

## Phase 5. Implementation

For each step, use a tight loop:

1. Write or adjust tests or checks first when it makes sense.
2. Implement the smallest useful change.
3. Run focused verification.
4. Refactor only if clarity improves without expanding scope.
5. Update the canonical document when design, scope, or criteria change.
6. Prepare a small commit when the step is complete.

### Common verification commands

Use only what applies:

```bash
uv sync
uv run pytest
uv run uvicorn app.main:app --reload
docker compose config
docker compose build
```

If there is no automated suite, say so explicitly and define a minimal manual check.

### Living documentation

Update the input document when:

- The technical plan changes.
- A relevant decision appears.
- A new edge case is found.
- An environment variable changes.
- Acceptance criteria are added or removed.
- A major milestone completes.

Do not let documentation drift more than one step behind the code.

---

## Phase 6. Completion and commit preparation

Before finishing:

- [ ] Run applicable verification.
- [ ] Review `git status`.
- [ ] Confirm no secrets or local artifacts are staged.
- [ ] Update the canonical document.
- [ ] Add or prepare the repository commits section if commits will follow.
- [ ] Propose commit grouping when there are multiple focuses.

If the user asks for commits, follow `/commit-pending`:

- Commit messages in English with conventional prefixes.
- Commit log table: headers may match existing docs; **descriptions in English** per base standards.
- Prefer logging commits in the feature document; push to `origin` when appropriate.

---

## Phase 7. Learnings and rules

When closing a task, check for learnings:

- **Feature-specific**: add to the canonical document.
- **Reusable**: create or update a note under `aprendizajes/`.
- **Project rule**: only if it applies across tasks, prevents repeat mistakes, and does not contradict existing rules.

Do not promote one-off anecdotes into permanent rules.

---

## Expected output when starting

After `/start-task`, respond with:

- Task summary.
- Canonical document identified.
- Task type.
- Rules read.
- Relevant files or areas.
- Risks or open decisions.
- Baby-steps plan.
- Proposed verification.
- Where progress and commits will be recorded.

## Common scenarios

### Incomplete document

Fill obvious gaps; ask only for blocking decisions. Include a suggestion, in English:

```text
The document does not name an LLM model. I suggest defaulting to `gpt-4o-mini` as a low-cost baseline because it appears in `.env.example`. Confirm?
```

### Scope creep

When new work appears:

- If small, extend the plan and document the change.
- If large, park it under `Out of Scope` or `Future Work`.
- Do not merge unrelated features without explicit agreement.

### No tests yet

If tests do not exist:

- Define a minimal manual verification path.
- Propose tests once the code surface is stable.
- Do not assume `pytest` is configured if it is not.

### External dependency

Before adding a dependency:

- Check for an existing alternative in the repo.
- Justify why it is needed.
- Add it with `uv`.
- Update `pyproject.toml`, lockfile, and documentation.

## Integration with other commands

- Before: `/write-feature` or `/requirement-write` to create the document if it does not exist.
- Before implementation: `/requirement-validate` if the note is still vague.
- For non-trivial changes: `/requirement-design` and `/requirement-tasks`.
- During validation: `/check-quality`, `/check-architecture`, `/testing`, and `/check-dod`.
- During: `/docs` to sync README, decisions, and sessions.
- After: `/commit-pending` for traceable commits in the feature document.
- Learning-focused work: `/master-tutor` when the main goal is understanding a master-class concept.

## Success criteria

`/start-task` succeeds when:

- The input document is identified as the canonical source.
- The task is scoped and no hidden blockers remain.
- Relevant rules were read.
- The plan is small, verifiable, and aligned with the repo.
- Documentation and commit logging destinations are clear.
- Coding did not start without enough context.

**Last updated:** 2026-04-27
