# write-front-feature

## Purpose

Create an **implementation-ready front-end feature specification** before `/start-front-task`.

This command should think like a **Senior Frontend Engineer + Product Designer** and produce the most detailed, design-aware spec possible for the front end.

**This command writes documentation only.** It does not implement the feature.

## When to Use

Use for features where the primary work is user-facing front-end behavior, such as:

- New pages, screens, or flows
- UI refinements or redesigns
- Responsive layouts
- Component-level interactions
- Empty, loading, error, and success states
- Accessibility or usability improvements
- Product flows that need clear interaction and visual design decisions

## When NOT to Use

- The user wants to **implement** now -> use `/start-front-task` with the work item path.
- The work is clearly backend-only, infra-only, or LLM-only -> use `/write-feature` or the appropriate work item type instead.
- The user wants a bugfix, ADR, or experiment -> use the appropriate work item prefix, not `front-feature-`.

## Ambiguous prompts

User prompts are often long and mix **design**, **product**, and **implementation** language.

**Default:** treat `/write-front-feature` as **spec-only**, regardless of wording like "implement", "build", "code", or "tests", unless **all** of the following are true:

1. The user **explicitly** asks to implement **in this turn** (not "prepare for later"), and
2. The user **explicitly** asks to run `/start-front-task` or says to skip the spec and code now.

If the request is missing key UI details, do **not** invent them silently. Capture the gap in the spec and, if needed, ask focused follow-up questions about:

- Primary user and use case
- Target device or viewport assumptions
- Visual direction or design references
- Existing design system or brand constraints
- Required states, edge cases, and content rules
- Success criteria for the experience

If there is **any doubt**, stop and ask before writing code:

> "¿Quieres solo el work item en `docs/work-items/` (recomendado con `/write-front-feature`), o que arranque la implementación con `/start-front-task` sobre ese documento?"

Do **not** infer implementation intent from a detailed requirements list alone.

## Implementation rule (mandatory)

- **Never** implement the feature during `/write-front-feature` -> no new pages, components, styles, tests, or app wiring.
- The **only** allowed repo changes are the canonical Markdown work item (and, if the user explicitly asks, related doc tweaks such as cross-links).
- If the user wants implementation, respond with the work item path and tell them to run:

```text
/start-front-task docs/work-items/front-feature-NNN-<slug>.md
```

All production code, tests, commits, and PR setup belong to `/start-front-task`, not `/write-front-feature`.

## Destination

Create exactly one canonical work item under:

```text
docs/work-items/front-feature-NNN-<kebab-slug>.md
```

Use the next free `NNN` in `docs/work-items/` by scanning **all** work items with a numeric prefix (`feature-NNN-*.md`, `front-feature-NNN-*.md`, and other typed prefixes) and incrementing the **highest** number. Do not create `feature-NNN-*.md` for front-primary work (use `front-feature-` instead) or legacy filenames such as `feature-<slug>.md`.

## Required Workflow

1. Read relevant rules:
   - `.cursor/rules/00-base-standards.mdc`
   - `.cursor/rules/01-python-standards.mdc` when supporting app structure is relevant
   - `.cursor/rules/02-fastapi-standards.mdc` when the front end depends on API contracts
   - `.cursor/rules/03-ai-engineering-standards.mdc` when LLM-driven UI or prompts are involved
   - `.cursor/rules/04-environment-and-secrets.mdc` when settings or secrets are involved
   - `.cursor/rules/05-testing-standards.mdc`
   - `.cursor/rules/07-pre-implementation-analysis.mdc`
   - `.cursor/rules/09-requirement-validation-workflow.mdc`
   - `.cursor/rules/11-spec-system.mdc`
2. Gather context from existing code, UI patterns, design docs, and related work items in read-only mode.
3. Identify the next `NNN` and write one canonical feature document in `docs/work-items/`.
4. Make the spec rich enough that `/start-front-task` can implement the front-end experience without guesswork.
5. **Do not** implement the feature. **Do not** edit application code or tests.

## Required Structure

```markdown
# Feature: [Name]

## Objective
What user problem is being solved and why this front-end experience matters.

## Context
Existing UI patterns, routes, components, design-system constraints, API dependencies, and product background.

## Product Goal
The expected user outcome, business value, or product behavior change.

## Users and Use Cases
- Primary user:
- Secondary user:
- Core scenario:
- Adjacent scenario:

## Scope
### Includes
- ...

### Excludes
- ...

## UX Principles
- Interaction model:
- Information hierarchy:
- Feedback strategy:
- Error recovery:
- Trust and clarity:

## User Flow
Describe the ideal path step by step, including entry points and exit points.

## UI/Interaction Requirements
Concrete front-end behavior, transitions, affordances, and interaction rules.

## Layout and Information Architecture
How the screen or flow should be structured, section by section.

## Visual Direction
Design intent, spacing, density, emphasis, hierarchy, and any brand or aesthetic guidance.

## Responsive Behavior
Desktop, tablet, mobile, and any breakpoint-specific differences.

## Accessibility Requirements
Keyboard support, focus states, semantics, contrast, screen-reader behavior, motion preferences, and readable copy.

## Content and Copy
Text, labels, empty states, helper text, errors, and content constraints.

## States
### Loading
### Empty
### Error
### Partial / Disabled
### Success
### Permission / Auth

## Data and API Dependencies
Inputs from backend, expected response shape, caching or loading assumptions, and contract risks.

## Technical Approach
Front-end architecture, components, state ownership, routing, data fetching, and integration points.

## Design and Implementation Notes
Tokens, reusable components, animations, localization, theming, analytics, and feature flags if relevant.

## Acceptance Criteria
- [ ] AC-01: ...
- [ ] AC-02: ...
- [ ] AC-03: ...
(...) target a detailed set of criteria for the UI, behavior, states, and accessibility

## Test Plan
- Unit tests:
- Component tests:
- Contract tests:
- Manual checks:

## Verification
- Automated:
- Manual:
- Not verified yet:

## Documentation Plan
What must be reflected in README, UI docs, Storybook, or Second Brain.

## Implementation Plan
- [ ] Step 1:
- [ ] Step 2:
- [ ] Step 3:
```

Optional but recommended:

- `## Design Notes` for references, trade-offs, or visual inspiration.
- `## Open Questions` for unresolved product or UX decisions.
- `## Learnings` for pitfalls from prior attempts or related features.
- Placeholders: `## Estimation`, `## Implementation progress`, `## Pull Request` (filled during `/start-front-task`).

## Rules

- Make the spec complete enough to pass `/start-front-task`'s front-end documentation gate.
- Keep specs detailed, but avoid inventing product requirements that were never stated.
- Prefer explicit front-end states over vague behavior.
- Include responsive and accessibility requirements whenever the UI is user-facing.
- Include real API names or UI components only if they exist in the codebase.
- Mention environment variables if the feature uses external APIs.
- Never include real API keys in the document.
- Do not add `## Repository commits (master-ia)` during initial writing; that section is added during task completion as an implementation report.

## Completion checklist

Before finishing `/write-front-feature`, confirm:

- [ ] Exactly one new/updated file under `docs/work-items/front-feature-NNN-*.md`
- [ ] No changes under `app/`, `tests/`, or other implementation files unless explicitly requested outside this command
- [ ] User told how to start implementation: `/start-front-task docs/work-items/front-feature-NNN-<slug>.md`
