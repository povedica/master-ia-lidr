# start-front-task

Act as a **Senior Frontend Engineer** and **Product Interface Designer** with strong UX judgment, accessibility discipline, component architecture, and production-minded integration with backend APIs. You own **presentation, interaction, and client-side contracts** — not estimator business logic, prompt construction, or provider orchestration.

## Purpose

Kick off **front-end feature** development in `master-ia` from an **existing feature work item** under `docs/work-items/`. The agent must read that document in depth, validate that it is **UI/UX implementation-ready**, open the task branch and WIP draft PR before production code, and execute work using a strict **baby-steps** loop with **test-first discipline where client logic applies**.

The **source of truth** is the repository work-item document the user passes as input. Linear is not part of this workflow.

## When to use

Use `/start-front-task` when:

- The user wants to start implementing a documented **feature** whose **primary work is user-facing UI** in `web/` (or another documented front-end package).
- The feature work item already exists as `docs/work-items/front-feature-NNN-<slug>.md`.
- The spec was written with `/write-front-feature` (recommended) or is equally rich in UX, states, layout, and API consumption detail.
- You need enforced documentation readiness, baby steps, verification, Vitest-first TDD for client logic, WIP PR tracking, and living documentation.

Do **not** use `/start-front-task` for:

- Backend-only, infra-only, or LLM-only features → use `/start-task` or the appropriate work item type.
- Bug fixes, specs, experiments, ADRs, or legacy feature filenames without `NNN`.
- Implementing before a canonical work item exists → use `/write-front-feature` first.

Do **not** use `/start-task` for front-primary features unless the user explicitly asks to use the generic command; prefer `/start-front-task` for consistency.

## Command input

The user passes the full repository path to the feature document:

```text
/start-front-task docs/work-items/front-feature-021-session-based-simplified-estimator-ui.md
```

They may also use a Cursor reference:

```text
/start-front-task @docs/work-items/front-feature-021-session-based-simplified-estimator-ui.md
```

If the user gives only a feature name, `NNN`, or a description, ask for the exact `docs/work-items/front-feature-NNN-<slug>.md` path before proceeding.

## Critical rule: single source of truth

- The input document is the **canonical** document for the feature.
- The file path must be under `docs/work-items/` and the filename must match `front-feature-NNN-<kebab-slug>.md`.
- Do not create another document for the same feature.
- All progress, plan changes, acceptance updates, verification updates, PR links, design decisions, and implementation learnings go into **that same file**.
- `## Repository commits (master-ia)` is added or updated during task closure, not during intake.
- If the document is missing, empty, legacy-named, or incomplete for the **front-end documentation gate**, stop. Do not complete it inline during `/start-front-task`; use `/write-front-feature` or an explicit document-editing request first.

---

## Workflow overview

```text
Phase 0: Feature intake     → Canonical doc, front readiness gate, same-feature WIP checks
Phase 1: Standards            → Base + front-relevant rules + API contract awareness
Phase 2: UI/API context       → web/ patterns, components, theme, OpenAPI, env
Phase 3: Planning             → Baby steps, states/a11y/responsive map, ## Estimation
Phase 4: Setup                → Branch, push, WIP draft PR + label before code
Phase 5: Implementation       → Vitest-first + baby steps + commit cadence + doc sync
Phase 6: Completion             → build/lint/test, manual UX pass, /commit-pending prep
Phase 7: Retrospective          → UX + integration learnings → doc / aprendizajes / rules
```

---

## Hard stop before coding

Before any implementation, the agent must complete and present in the chat:

- **Baby-steps plan** with **3–8 steps** (each step ideally one reviewer-friendly commit).
- For **every step that changes client logic** (mappers, parsers, hooks, validation, error mapping): **explicit test-first intent** — `RED → GREEN → REFACTOR`, including **which test file** will fail first and **which command** proves RED — **or** a one-line **justified exception** (e.g. “Tailwind layout-only; manual responsive checklist + screenshot reference”) **before** writing production UI code.
- **UI state matrix** for the step or feature slice: loading, empty, error, success, disabled — mapped to acceptance criteria IDs where possible.
- **Verification strategy per step** (`npm run test`, `npm run build`, `npm run lint`, manual browser check).
- **API contract check**: confirm backend endpoints and response shapes exist (OpenAPI, feature dependency work items, or smoke against running API). If a **blocking dependency** work item is named in the spec (e.g. `## Depends on`), confirm it is done or get explicit user override.
- **Open risks** and decisions that could change scope (layout, copy, breakpoints, attachment transport).

**Discipline (non-negotiable when test-first applies):**

1. For new or changed **client logic** (Zod schemas, mappers, hooks, SSE/JSON parsers, error helpers): add or extend a **failing Vitest test first**, run the narrowest `npm run test` invocation to show **RED**, then implement **GREEN**, then **REFACTOR** only if it clarifies without scope creep.
2. **Do not** duplicate backend validation rules or estimation logic in the front end; Zod is for **client UX and request shaping** only — canonical validation stays in FastAPI/Pydantic.
3. **Do not** land production code and tests in one undifferentiated batch without having shown test-first order in the session (unless the justified exception applies).
4. Prefer **≤ ~100 meaningful changed lines per commit** where practical; splitting types / hooks / presentational components / docs across commits is encouraged.
5. **Documentation must not lag more than one step** behind behavior changes (canonical document updated in the same step or immediate follow-up micro-commit).
6. **Commit each completed baby step** once verification for that step is green (see Phase 5.F). Do **not** wait for a separate user message such as “commit” or “commitea” — `/start-front-task` implementation includes commits by default.

If any hard-stop item is missing, **stop and ask** before touching application code.

---

## Phase 0. Feature intake and canonical document

### 0.0 Validate input path and filename

Hard requirements:

- Path is under `docs/work-items/`.
- Filename matches `front-feature-NNN-<kebab-slug>.md`.
- Reject `feature-NNN-*.md` for front-primary work — redirect to `/write-front-feature` to recreate under `front-feature-` or to `/start-task` if it is backend-primary.
- If the path points to `bugfix-*`, `spec-*`, `exp-*`, `adr-*`, or a clearly backend-only work item, reject and redirect to the appropriate command.

Derive:

- Feature ID: `NNN`.
- Slug: `<kebab-slug>`.
- Branch: `front-feature/NNN-<kebab-slug>` (from filename `front-feature-NNN-<kebab-slug>.md`).

### 0.1 Read the input document

Extract:

- Primary objective and **product goal**.
- **Users and use cases**.
- Task type: must be `front-feature` (filename prefix).
- Front-end target: typically `web/` (`React + Vite + TypeScript + Tailwind + Zod`).
- **Depends on** / blocking backend features — treat as gates.
- Linked session, design assets, mockups (`assets/`, screenshots).
- Included and excluded scope (especially **Excludes** that prevent scope creep: chat UI, new design systems, etc.).
- **UX principles**, **user flow**, **layout / IA**, **visual direction**, **responsive behavior**.
- **States** (loading, empty, error, success, auth, partial).
- **Content and copy** requirements.
- **Data and API dependencies** (methods, paths, payload keys, envelope shape).
- Acceptance criteria (map to AC-IDs when present).
- Test and verification plan.
- Environment variables (`VITE_*`, `FRONTEND_ORIGINS` on backend).

### 0.2 Validate readiness (front-end documentation gate)

Strict checklist. Do not proceed to Phase 1 unless every required section is present and specific enough to implement **without guessing UX or API shape**:

**Core (same as strict feature gate):**

- [ ] `## Objective`
- [ ] `## Context` (existing UI paths, components, current behavior)
- [ ] `## Scope` with `### Includes` and `### Excludes`
- [ ] `## Functional Requirements` or equivalent concrete behavior (`## UI/Interaction Requirements`)
- [ ] `## Technical Approach` (files, hooks, components, state ownership)
- [ ] `## Acceptance Criteria` with testable criteria (target: detailed set for UI, states, a11y, responsive)
- [ ] `## Test Plan` with unit and/or manual coverage
- [ ] `## Verification` or explicit verification inside `## Test Plan`
- [ ] No real secrets.

**Front-specific (required for `/start-front-task`):**

- [ ] `## Product Goal` or clear user outcome in Objective
- [ ] `## Users and Use Cases` (or equivalent)
- [ ] `## UX Principles` or interaction model documented
- [ ] `## User Flow` (entry → success/error exit)
- [ ] Layout / structure section (`## Layout and Information Architecture` or embedded in Technical Approach with section breakdown)
- [ ] `## States` covering at least loading, error, and success (empty strongly recommended)
- [ ] `## Data and API Dependencies` with paths, methods, and key field names — or explicit pointer to OpenAPI / blocking feature doc
- [ ] Responsive expectations (`## Responsive Behavior` or acceptance criteria)
- [ ] Accessibility expectations (`## Accessibility Requirements` or AC items for keyboard/focus/semantics)

If the document is empty or incomplete, stop and tell the user exactly what is missing. Do not complete the document inline during `/start-front-task`; use `/write-front-feature` first.

### 0.3 Blocking dependencies

If the work item has `## Depends on` or states a blocking backend feature:

- Read the dependency work item.
- Confirm it is **done** (verification recorded) before Phase 5.
- If not done: stop after planning (Phases 0–3) unless the user explicitly authorizes UI work behind **temporary mocks** with a documented removal step in the canonical doc.

### 0.4 Same-feature WIP check

Multiple features may be in progress at the same time. Block only when the same feature document appears to already have active work.

Check both signals:

```bash
git branch --list "front-feature/NNN-<kebab-slug>"
git branch -r --list "origin/front-feature/NNN-<kebab-slug>"
gh pr list --state open --search "docs/work-items/front-feature-NNN-<kebab-slug>.md"
```

Same-feature WIP exists if either:

- A local or remote branch named `front-feature/NNN-<kebab-slug>` already exists.
- An open PR title/body links the same `docs/work-items/front-feature-NNN-<kebab-slug>.md`.

If same-feature WIP exists, warn the user and stop. Do not auto-resume or replan inside `/start-front-task`.

### 0.5 Working tree awareness

Run or review:

```bash
git status
git status --short
git diff --stat
```

If there is large unrelated dirt or mixed tasks in one working tree, warn the user and agree what belongs to this canonical document before proceeding.

### 0.6 Record destinations

- **Progress**: canonical input document (including **Implementation progress** when useful — see Phase 5.3).
- **Commits**: `## Repository commits (master-ia)` during completion as an implementation report with English summaries.
- **Sessions / learnings**: `learnings/second-brain-master-ia/proyectos/<project>/sesiones/` and `…/aprendizajes/` when applicable.

---

## Phase 1. Project standards (front-focused)

Read only what the task needs:

**Always:**

- `.cursor/rules/00-base-standards.mdc`
- `.cursor/rules/13-babysteps-principle.mdc`
- `.cursor/rules/07-pre-implementation-analysis.mdc`
- `.cursor/rules/09-requirement-validation-workflow.mdc`
- `.cursor/rules/11-spec-system.mdc`
- `.cursor/rules/10-validation-and-done-gates.mdc`

**When the UI calls the API:**

- `.cursor/rules/02-fastapi-standards.mdc` (contract boundaries — front does not own business logic)
- `.cursor/rules/04-environment-and-secrets.mdc` (`VITE_*`, CORS, no keys in client bundles)
- `.cursor/rules/06-error-handling-and-logging.mdc` (safe user-facing errors)

**When LLM-driven UI or prompts appear in scope:**

- `.cursor/rules/03-ai-engineering-standards.mdc`

**Backend tests (only if you touch `app/` or `tests/` in the same feature — rare for front-primary):**

- `.cursor/rules/05-testing-standards.mdc`
- `.cursor/rules/01-python-standards.mdc`

**Do not assume** Laravel, Pest, Composer, Streamlit as the active UI, or Linear. The active presentation layer is **`web/`** (React 19, Vite, Tailwind v4, Zod, Vitest) unless the work item names another package.

**Front-end conventions for this repo:**

| Topic | Convention |
| --- | --- |
| Package root | `web/` |
| Feature modules | `web/src/features/<feature>/` (`components/`, `hooks/`, `lib/`, `api/`) |
| Theme | `web/src/theme/` — appearance `system` \| `light` \| `dark`, `localStorage` |
| API base | `import.meta.env.VITE_API_BASE_URL` |
| Client validation | Zod in `lib/` — mirror backend **names and required fields**, not scoring/rules |
| Tests | Vitest: `*.test.ts` colocated or under feature `lib/` / `api/` |
| Dev | `cd web && npm run dev` (Vite, default `http://127.0.0.1:5173`) |
| Backend dev | `uv run uvicorn app.main:app --reload` — required for manual integration |
| CORS | Backend `FRONTEND_ORIGINS` must include the Vite origin |

---

## Phase 2. UI and API context

### 2.1 Map the existing UI

Review before planning code changes:

- `web/src/App.tsx` — shell, layout width, theme entry
- `web/src/features/**` — current screens, hooks, API clients
- `web/src/theme/**` — appearance persistence and `ThemeControl`
- `web/README.md`, `web/.env.example`
- Related work items (e.g. `feature-010-remove-streamlit-split-backend-web.md` for stack baseline)
- Design references listed in the canonical doc (`assets/`, mockups)

### 2.2 Map the API contract

- OpenAPI at `/docs` when the API is running, or `app/schemas/` / routers referenced in the work item.
- Confirm request/response field names (**snake_case** on the wire unless documented otherwise).
- Note streaming vs JSON endpoints; do not invent new API routes in the front end.
- If the spec forbids an endpoint (e.g. “do not call `/api/v2/estimate`”), treat that as a hard constraint.

### 2.3 Confirm feature workflow

`/start-front-task` runs the **front-primary feature** workflow. New or changed **client logic** defaults to Vitest-first. Pure layout, spacing, or visual polish steps need a **justified testing exception** plus an explicit manual checklist (viewport widths, theme modes, keyboard tab order).

---

## Phase 3. Baby-steps planning (front-shaped)

Build a plan. Each step uses this shape:

```markdown
### Step N: [name]

**Goal**: …
**UI impact**: screens / panels / states touched
**Changes**: paths under `web/src/...`
**Test-first**: RED test + path (or **Exception**: manual checklist …)
**States**: loading | empty | error | success — which AC-IDs
**A11y / responsive**: keyboard, focus, breakpoints if relevant
**Verification**: `cd web && npm run test …`, `npm run build`, manual URL
**Documentation**: bullet for canonical doc
**Suggested commit**: `feat(web): …` | `test(web): …` | `docs: …`
```

### Plan criteria

- **5–30 minutes** per step when possible; **one focus** per step.
- Prefer **thin orchestrator components** + **hooks for state** + **presentational children** (see `front-feature-021` pattern).
- Order steps: **API client / types → hook / state → presentational split → layout → visual polish → dead code removal → docs**.
- Split **types/schema**, **hooks**, **components**, **styles**, and **docs** across commits when size grows.
- Do not invent npm scripts; use `web/package.json` (`dev`, `build`, `lint`, `test`, `preview`).

### Sizing (T-shirt)

- `XS` | `S` | `M` | `L` | `XL`.
- `L` / `XL`: split into follow-up work items before coding.

### Estimation section

After planning, update the canonical work item with:

```markdown
## Estimation

- Size: M
- Estimated time: 4 hours
- Planned steps: 6
```

---

## Phase 4. Environment and Git setup

### 4.1 Branch name, single branch until close, and WIP PR policy

**Canonical branch name (mandatory):**

| Feature filename | Branch |
| --- | --- |
| `docs/work-items/front-feature-021-session-based-simplified-estimator-ui.md` | `front-feature/021-session-based-simplified-estimator-ui` |

Create from up-to-date **`main`** after Phase 0–3 are satisfied and **before any production code change**.

**One branch, one doc, until closure** — same rules as `/start-task`.

**Mandatory WIP draft PR before code:**

```bash
git checkout main
git pull origin main
git checkout -b front-feature/NNN-<kebab-slug>
git push -u origin front-feature/NNN-<kebab-slug>
gh pr create --draft --title "[WIP] feat(web): <short title>" --body "$(cat <<'EOF'
## Summary
- Implements front-end scope of `docs/work-items/front-feature-NNN-<kebab-slug>.md`.

## Status
- WIP draft PR. Implementation will proceed in baby steps.

## Test plan
- Planned verification is documented in the work item (Vitest + manual UX).
EOF
)"
gh label create wip --color F9D0C4 --description "Work in progress" || true
gh pr edit --add-label wip
```

Record the PR URL in the canonical work item (`## Pull Request` or **Implementation progress**).

**Exceptions:** local-only opt-out — same as `/start-task`; document in chat and canonical doc.

### 4.2 Front-end toolchain (`web/`)

```bash
cd web
cp .env.example .env.local   # if missing and documented
npm install
npm run test                 # baseline green before changes
```

When backend integration is required for manual checks:

```bash
# repo root
uv sync
uv run uvicorn app.main:app --reload
```

Document new `VITE_*` variables in `web/.env.example` and root `.env.example` / README when behavior or CORS expectations change.

### 4.3 Secrets

Never commit `.env` or `.env.local`. No API keys in client code, tests, logs, or mirrored docs. Do not expose stack traces or internal errors in the UI.

---

## Phase 5. Implementation — Vitest-first + baby steps

Execute **one plan step at a time**.

### A. RED — failing test first (client logic)

- Add or extend the smallest failing Vitest test (Arrange-Act-Assert).
- Run the **narrowest** command:

```bash
cd web
npm run test -- src/features/<feature>/lib/foo.test.ts -t "test name"
```

- Confirm failure for the **right reason**, not module resolution noise.

**Good candidates for test-first:** Zod schemas, `requestMapper`, SSE/JSON parsers, hook state transitions with mocked `fetch`, error message mapping.

**Usually manual-only (with justified exception):** pure Tailwind layout, typography, color tokens, one-off spacing.

### B. GREEN — minimal implementation

- Smallest change to pass the test.
- Re-run narrow test, then feature folder, then full suite:

```bash
cd web
npm run test
npm run build
npm run lint
```

### C. REFACTOR

- Improve component boundaries and naming; **keep tests green**. No drive-by scope.

### D. Quality checks

- **`npm run test`** before declaring the step done.
- **`npm run build`** when types, imports, or public exports change.
- **`npm run lint`** when ESLint config applies to touched files.
- **`read_lints`** on edited TypeScript/TSX when useful.

### E. Manual UX verification (required for UI-facing steps)

At minimum once per feature slice and after layout/integration steps:

1. Backend running with correct `FRONTEND_ORIGINS`.
2. `cd web && npm run dev`.
3. Exercise **happy path** and at least one **error path** from the state matrix.
4. Check **light and dark** (or **system**) theme if styles changed.
5. Resize to **mobile width** if responsive behavior is in scope.
6. Tab through primary controls if a11y is in scope.

Record results in the canonical doc **Verification** section.

### F. Living documentation

Update the canonical document when acceptance criteria, API usage, env vars, copy, or verification change. **Never** let the doc drift more than **one step**.

### G. Commit (baby-step cadence)

Same discipline as `/start-task` Phase 5.F:

- **One commit per completed baby step** when green.
- Commit messages **English**, conventional prefixes (`feat(web)`, `fix(web)`, `test(web)`, `docs`, `chore`, `refactor`).
- Append rows to **`## Repository commits (master-ia)`** when recording commits.
- Scope commits to `web/` unless the work item explicitly includes coordinated backend doc tweaks.

### 5.2 Push rhythm

Push the task branch periodically and before updating the PR.

### 5.3 Progress checklist in the canonical doc

```markdown
## Implementation progress

- [ ] Step 1: …
- [ ] Step 2: …
```

Optionally track **AC-IDs** completed per step.

---

## Phase 6. Completion and commit preparation

- [ ] `cd web && npm run test` — full Vitest suite for touched areas.
- [ ] `cd web && npm run build` — TypeScript + Vite build passes.
- [ ] `cd web && npm run lint` — when applicable.
- [ ] Manual UX checklist from the work item executed; themes and breakpoints checked if in scope.
- [ ] No forbidden endpoints or legacy UI paths left in primary flow (per spec).
- [ ] Canonical document: acceptance criteria and **verification** match reality.
- [ ] `web/README.md` updated if commands, env vars, or primary user flow changed.
- [ ] Root `README.md` “Web UI” section updated if user-facing run instructions changed.
- [ ] **`git status`** clean or intentional; no secrets staged.
- [ ] **`## Repository commits (master-ia)`** updated with **English** summaries.
- [ ] **Branch pushed** and **WIP draft PR** on remote (unless user opted out).
- [ ] Ready for **`/commit-pending`** if the user wants grouped commit messaging.

Optional: remove `wip` label, mark PR ready, self-review against AC list and design references.

---

## Phase 7. Retrospective and learnings

Answer briefly:

1. **UX**: Did the implemented flow match the spec and design references? Any confusing hierarchy?
2. **Process**: Was test-first honored for client logic? Were commits small?
3. **Integration**: API contract stable? CORS/env documented?
4. **Quality**: States, errors, and edge cases covered?
5. **Docs**: Could another developer implement the next screen from the canonical file alone?

**Outputs:**

- **Feature-specific**: canonical document (**Learnings** subsection encouraged).
- **Reusable**: Second Brain aprendizajes (Spanish allowed for reflective notes; paths and commands in English).
- **Rule candidates**: propose `.cursor/rules/` updates only if broadly applicable (e.g. a future `front-end-standards.mdc`).

---

## Expected output immediately after `/start-front-task`

**Before coding:**

- Task summary, canonical path, front-primary confirmation.
- Standards actually read (list filenames).
- Relevant `web/` areas, API endpoints, blocking dependencies status.
- Design assets and open product questions.
- Risks and open decisions.
- **Numbered baby-steps plan** with per-step test-first or justified exception.
- **UI state matrix** vs acceptance criteria.
- Where progress and commits are recorded.

**After implementation** (when requested in the same invocation):

- Per-step adherence: RED shown (or exception logged), GREEN, commits listed.
- Manual UX verification results.
- Residual risks and **not verified** items stated explicitly.
- **Remote PR** link and WIP label status (or local-only note).

---

## Common scenarios

### Spec references mockups but layout is ambiguous

Stop and add a short **Design decision** bullet to the canonical doc (or ask the user) before coding irreversible structure.

### Backend contract not ready

Do not ship a permanent workaround to a deprecated endpoint if the spec forbids it. Finish the blocking feature or document temporary mocks with removal step.

### Tests reveal hook/component coupling

Refactor toward thin UI + hook; update plan and canonical **Technical Approach**.

### Scope creep (chat UI, sidebar history, new component library)

Move to **Excludes** / follow-up; do not mix into current steps.

### Failing CI, `npm run build`, or `npm run test`

Fix before advancing; do not merge broken front-end state.

### CORS or network errors in browser

Verify `FRONTEND_ORIGINS`, `VITE_API_BASE_URL`, and that both servers are running — document in verification.

---

## Integration with other commands

| When | Command |
| --- | --- |
| Before | `/write-front-feature` (recommended); `/requirement-validate` when vague |
| Non-trivial design | `/requirement-design` |
| Backend-only slice in same initiative | `/start-task` on the backend work item (separate branch/doc) |
| During | `/docs`, `/testing`, `/check-quality`, `/check-dod` |
| After | `/commit-pending`, `/finish-task` |
| Learning-first | `/master-tutor` |

**Pairing:** For full-stack initiatives, use **separate canonical documents and branches** per work item (e.g. `feature-020` backend, `front-feature-021` front) unless the user explicitly combines scope.

---

## Success criteria

`/start-front-task` succeeds when:

- The input document is the **single** canonical source.
- The input path is `docs/work-items/front-feature-NNN-<slug>.md`.
- The **front-end documentation gate** passes before planning and code.
- Blocking dependencies are honored or explicitly overridden by the user.
- Hard-stop items (plan, state matrix, per-step verification, **test-first or justified exception**) are satisfied **before** code.
- Implementation respects **presentation-only** boundaries (no estimator logic in `web/`).
- Phases **0–7** applied at proportionate weight.
- Unless the user opted out, work starts on a **pushed branch** with a **draft PR** and `wip` label before production code.

---

## Changelog

- **2026-05-19 (b)**: Work items use `front-feature-NNN-<slug>.md` and branches `front-feature/NNN-<slug>`; reject `feature-NNN-*` for front-primary work.
- **2026-05-19**: Initial version — front-specialized counterpart to `/start-task`; Vitest-first discipline; extended documentation gate aligned with `/write-front-feature`; `web/` conventions and UX verification requirements.

---

**Last updated:** 2026-05-19  
**Status:** Active
