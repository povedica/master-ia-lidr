# write-feature

## Purpose

Create an **implementation-ready feature specification** before `/start-task`.

**This command writes documentation only.** It does not implement the feature.

## When to Use

Use for a new API endpoint, service, LLM workflow, script, project setup, or reusable capability.

## When NOT to Use

- The user wants to **implement** now → use `/start-task` with the work item path.
- The user wants a bugfix, ADR, or experiment → use the appropriate work item prefix, not `feature-`.

## Ambiguous prompts

User prompts are often long and mix **spec** language with **implementation** language (e.g. "write-feature … I want you to implement …").

**Default:** treat `/write-feature` as **spec-only**, regardless of wording like "implement", "build", "code", or "tests", unless **all** of the following are true:

1. The user **explicitly** asks to implement **in this turn** (not "prepare for later"), **and**
2. The user **explicitly** asks to run `/start-task` or says to skip the spec and code now.

If there is **any doubt**, **stop and ask** before writing code:

> "¿Quieres solo el work item en `docs/work-items/` (recomendado con `/write-feature`), o que arranque la implementación con `/start-task` sobre ese documento?"

Do **not** infer implementation intent from a detailed requirements list alone.

## Implementation rule (mandatory)

- **Never** implement the feature during `/write-feature` — no new routers, services, tests, or `main.py` wiring.
- The **only** allowed repo changes are the canonical Markdown work item (and, if the user explicitly asks, related doc tweaks such as cross-links).
- If the user wants implementation, respond with the work item path and tell them to run:

```text
/start-task docs/work-items/feature-NNN-<slug>.md
```

All production code, tests, commits, and PR setup belong to `/start-task`, not `/write-feature`.

## Destination

Create exactly one canonical work item under:

```text
docs/work-items/feature-NNN-<kebab-slug>.md
```

Use the next free `NNN` in `docs/work-items/` by scanning existing `feature-NNN-*.md` files and incrementing the highest number. Do not create legacy filenames such as `feature-<slug>.md`.

## Required Workflow

1. Read relevant rules:
   - `.cursor/rules/00-base-standards.mdc`
   - `.cursor/rules/02-fastapi-standards.mdc` when API work is involved
   - `.cursor/rules/03-ai-engineering-standards.mdc` when LLM work is involved
   - `.cursor/rules/04-environment-and-secrets.mdc` when settings or secrets are involved
   - `.cursor/rules/05-testing-standards.mdc`
2. Gather context from existing code and docs (read-only).
3. Pick the next `NNN` and write one canonical feature document in `docs/work-items/`.
4. Include strict readiness sections for `/start-task`'s documentation gate, baby steps, verification, and **learnings / pitfalls** when revising an existing area.
5. **Do not** implement the feature. **Do not** register routers or edit `app/` except if the user explicitly requested a non-feature doc change in the same message.

## Required Structure

```markdown
# Feature: [Name]

## Objective
What is being built and why.

## Context
Existing code, similar patterns, constraints.

## Scope
### Includes
- ...

### Excludes
- ...

## Functional Requirements
Concrete behavior, inputs, outputs, and examples.

## Technical Approach
FastAPI route, service, LLM client, settings, data flow.

## Acceptance Criteria
- [ ] AC-01: ...
- [ ] AC-02: ...
(... target ~10+ for non-trivial features)

## Test Plan
- Unit tests:
- Integration tests:
- Manual checks:

## Verification
- Automated:
- Manual:
- Not verified yet:

## Documentation Plan
What must be reflected in README or Second Brain.

## Implementation Plan
- [ ] Step 1:
- [ ] Step 2:
- [ ] Step 3:
```

Optional but recommended for `/start-task`:

- `## Learnings` — pitfalls from prior attempts or related features.
- Placeholders: `## Estimation`, `## Implementation progress`, `## Pull Request` (filled during `/start-task`).

## Rules

- Make the spec complete enough to pass `/start-task`'s strict documentation gate (see `.cursor/commands/start-task.md` §0.2).
- Keep specs concise enough to implement from.
- Include `uv` commands when execution is relevant.
- Mention environment variables if the feature uses external APIs.
- Reference **real** APIs in the codebase (e.g. `complete_structured`, not invented helpers).
- Never include real API keys in the document.
- Do not add `## Repository commits (master-ia)` during initial writing; that section is added during task completion as an implementation report.

## Completion checklist

Before finishing `/write-feature`, confirm:

- [ ] Exactly one new/updated file under `docs/work-items/feature-NNN-*.md`
- [ ] No changes under `app/`, `tests/`, or `main.py` unless explicitly requested outside this command
- [ ] User told how to start implementation: `/start-task docs/work-items/feature-NNN-<slug>.md`
