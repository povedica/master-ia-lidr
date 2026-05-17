# write-feature

## Purpose
Create an implementation-ready feature specification before `/start-task`.

## When to Use
Use for a new API endpoint, service, LLM workflow, script, project setup, or reusable capability.

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
2. Gather context from existing code and docs.
3. Pick the next `NNN` and write one canonical feature document in `docs/work-items/`.
4. Include strict readiness sections, baby steps, and verification.
5. Do not implement the feature unless the user explicitly asks.

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
- [ ] AC-03: ...
- [ ] AC-04: ...
- [ ] AC-05: ...
- [ ] AC-06: ...
- [ ] AC-07: ...
- [ ] AC-08: ...
- [ ] AC-09: ...
- [ ] AC-10: ...

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

## Rules
- Make the spec complete enough to pass `/start-task`'s strict documentation gate.
- Keep specs concise enough to implement from.
- Include `uv` commands when execution is relevant.
- Mention environment variables if the feature uses external APIs.
- Never include real API keys in the document.
- Do not add `## Repository commits (master-ia)` during initial writing; that section is added during task completion as an implementation report.
