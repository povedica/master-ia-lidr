# Feature: Internal Retrieval Debug Screen (React)

> Sub-feature 6 of 7 of the epic `feature-041-retrieval-debug-observability-screen`.
> Depends on: `feature-042`…`feature-046` (the full debug API surface). 045 (rerank lane) recommended; the screen degrades gracefully if a branch is absent.
> Internal tooling. Not user-facing.

## Why this sub-feature

The debug API (042–046) is powerful but only usable via curl/Swagger. The headline deliverable of the epic is an operator-facing screen that makes retrieval tunable interactively: enter a query, switch strategies, adjust knobs, and *see* the comparative ranking, the diff, and per-result explanations side by side. Without the UI, the analytical value of the API stays locked behind JSON.

## Objective

Build an internal React screen in `web/` that consumes the debug API and implements requirements A–G of the epic (query box, tuning controls, comparative results, explainability, branch view, ranking diff, chunk inspection), with robust loading/error/empty/partial states and recent-search reuse, gated behind an env flag so it never reaches end users.

## Value increment (what ships and why it matters)

- A working internal route (e.g. `/debug/retrieval`) where an operator can interactively diagnose and tune retrieval.
- Visual comparative table, per-branch tabs, ranking diff, explanation chips, and a chunk inspector drawer.
- Result: the epic's promise — retrieval is no longer a black box — is realized for humans, not just for APIs.

## SMART framing

- **Specific:** one gated route + the A–G components + typed API client + Zod schemas.
- **Measurable:** AC-01…AC-12; component tests with mocked API; all states rendered.
- **Achievable:** reuses `web/` stack (React 19, Vite 8, Tailwind 4, Zod, Vitest) and existing API-client patterns.
- **Relevant:** the operator-facing deliverable of the epic.
- **Time-boxed:** Size L, ~6 baby steps.

## Context

- `web/` stack: React 19 + TS + Vite 8 + Tailwind 4 + Zod + Vitest; API clients live under `web/src/features/...` (e.g. `estimateApi.ts`, `sessionApi.ts`). No retrieval/admin screen exists.
- Backend contract is fixed by 042–046; mirror it with Zod schemas.
- Gate via `VITE_ENABLE_RETRIEVAL_DEBUG`; exclude from end-user navigation.

## Scope

### Includes

- `web/src/features/retrieval-debug/`:
  - `api/retrievalDebugApi.ts` + Zod schemas mirroring `RetrievalDebugRequest`/`RetrievalDebugResponse`/`ChunkInspectionResponse`.
  - `RetrievalDebugPage` shell with an explicit state machine: `idle` → `loading` → `results` | `empty` | `error` | `partial`.
  - Components (epic A–G): `QueryBox`, `TuningPanel`, `ComparativeResultsTable`, `ResultExplanation`, `BranchTabs`, `RankingDiffView`, `ChunkInspectorDrawer`.
  - Recent searches via `localStorage` (query + config), one-click reuse.
  - Env-gated route registration; hidden from end-user nav.
- Component tests (Vitest) with a mocked API for each state and key interactions.
- Frontend docs (README internal-tools + how to enable the flag).

### Excludes

- Backend changes (owned by 042–046); if a contract gap is found, fix it in the relevant backend sub-feature, not here.
- Persistence/export of runs, A/B config comparison (epic future extensions).
- Authn/authz beyond the env flag (documented follow-up).

## Functional Requirements (maps to epic A–G)

### FR-A — Query box

Natural-language input + Search button; strategy selector (`vector`/`lexical`/`hybrid`/`all`); recent searches list (localStorage) with reuse; Search disabled while loading.

### FR-B — Tuning controls

`top_k` per branch, semantic `threshold`, `max_results`, hybrid fusion (enable, method, `rrf_k`, weights), rerank toggle (placeholder — clearly labeled no-op when backend warns), metadata filters (document type, sector, technology, year range, source, tags, language). Controls map 1:1 to the request schema and respect documented bounds.

### FR-C — Comparative results

One row per `final_result`: final position, chunk id, source/document id, title, excerpt, semantic score/rank, lexical score/rank, fusion score, rerank score (if any), `source_strategies`, key metadata, and a visible reason (from explanation).

### FR-D — Explainability

Per-result explanation block: `summary` text + `signals` rendered as labeled chips (consensus, hybrid-rescued, semantic strong/weak, lexical exact-match, rerank promoted/demoted, below-threshold).

### FR-E — Branch view

Tabs/columns for vector / lexical / hybrid / rerank rankings; branches that are `null` render as "not run" rather than empty noise.

### FR-F — Ranking diff

Render `diff`: common, vector-only, lexical-only, hybrid-rescued, big movers (with from→to), dropped-by-threshold, dropped-by-rerank.

### FR-G — Chunk inspection

Clicking a result opens a drawer (calls `GET /retrieval-debug/chunks/{id}?query=`): full content, previous/next chunk context, parent document, full metadata, embedding model, chunk type, distance/similarity, matched terms.

### FR-States

- Loading: per-branch progress / skeleton; Search disabled.
- Error: friendly messages for `422`/`503`/`5xx`; no stack traces.
- Empty: distinct "no results" vs "not searched yet".
- Partial: render available branches; show backend `warnings` (e.g. lexical failed, rerank no-op) as non-blocking notices.

## Technical Approach

- Mirror backend types with Zod; parse responses defensively and surface parse/validation errors as an error state.
- Keep `RetrievalDebugPage` as the state owner; child components are presentational + callbacks.
- Reuse existing fetch/client conventions and theme (dark/light/system) from `web/src`.
- Gate route mounting on `import.meta.env.VITE_ENABLE_RETRIEVAL_DEBUG`.

## Acceptance Criteria

- [ ] AC-01: An env-gated internal route renders the debug screen only when `VITE_ENABLE_RETRIEVAL_DEBUG` is enabled; it is absent from end-user navigation.
- [ ] AC-02: `QueryBox` submits query + strategy; recent searches persist in `localStorage` and reuse on click; Search disabled while loading.
- [ ] AC-03: `TuningPanel` exposes top-k, threshold, max results, hybrid fusion config, rerank toggle, and metadata filters mapped to the request schema with valid bounds.
- [ ] AC-04: `ComparativeResultsTable` shows all required per-result columns (position, ids, title, excerpt, semantic/lexical/fusion/rerank scores+ranks, strategies, metadata, reason).
- [ ] AC-05: `ResultExplanation` renders `summary` + `signals` chips from the controlled vocabulary.
- [ ] AC-06: `BranchTabs` shows vector/lexical/hybrid/rerank rankings; `null` branches show "not run".
- [ ] AC-07: `RankingDiffView` renders common / exclusive / hybrid-rescued / big-movers / dropped sets from `diff`.
- [ ] AC-08: `ChunkInspectorDrawer` opens on result click and shows content, neighbor context, parent document, metadata, embedding model, chunk type, distance, matched terms.
- [ ] AC-09: Loading, error (`422`/`503`/`5xx`), empty, and partial states each render correctly.
- [ ] AC-10: Backend `warnings` (lexical failure, rerank no-op) display as non-blocking notices.
- [ ] AC-11: Component tests (Vitest) cover each state and key interactions with a mocked API; suite green.
- [ ] AC-12: README documents enabling the flag and using the screen; it is clearly internal-only.

## Test Plan

- Component (Vitest, mocked API): results rendering; each state (loading/error/empty/partial); recent-search reuse; tuning-control → request mapping; diff rendering; chunk drawer open + neighbor context; warnings notices.
- Manual: with `VITE_ENABLE_RETRIEVAL_DEBUG` on and Compose backend, run vector/lexical/hybrid/all; toggle threshold/fusion/rerank/filters; inspect a chunk; verify states by simulating empty/invalid/DB-down.

## Verification

- Automated: `cd web && npm test` (or project equivalent) for the new feature.
- Manual: end-to-end against Compose backend; screenshots/notes per state.
- Not verified yet: real reranker UI behavior (depends on a future real reranker); accessibility audit (follow-up).

## Documentation Plan

- `README.md`: internal-tools section — enable `VITE_ENABLE_RETRIEVAL_DEBUG`, run web + API, how to read the screen.
- `docs/arquitectura-estimador-cag.html`: add the internal screen node (debug-scoped).
- Second Brain: session note with screenshots and tuning learnings.

## Implementation Plan

- [ ] Step 1: `retrievalDebugApi.ts` + Zod schemas mirroring the backend contract + parse tests.
- [ ] Step 2: `RetrievalDebugPage` shell + state machine + env-gated route + idle/loading/error/empty tests.
- [ ] Step 3: `QueryBox` (strategy + recent searches) + `TuningPanel` (controls → request) + tests.
- [ ] Step 4: `ComparativeResultsTable` + `ResultExplanation` + `BranchTabs` + tests.
- [ ] Step 5: `RankingDiffView` + `ChunkInspectorDrawer` (chunk inspector call) + partial/warnings handling + tests.
- [ ] Step 6: Docs sweep + manual end-to-end verification.

## Estimation

- Size: L
- Estimated time: 1-2 focused sessions
- Planned steps: 7
- Depends on 042-046; headline deliverable of the epic.

## Implementation progress

- [x] Step 1: Setup branch, planning, and WIP PR.
- [ ] Step 2: React/Vitest DOM test harness.
- [ ] Step 3: `retrievalDebugApi.ts` + Zod schemas.
- [ ] Step 4: `RetrievalDebugPage` shell, env gate, and state machine.
- [ ] Step 5: `QueryBox`, `TuningPanel`, and recent searches.
- [ ] Step 6: Comparative results, explanations, branch tabs, and ranking diff.
- [ ] Step 7: Chunk inspector, partial/warnings states, docs, and final verification.

## Pull Request

- Draft PR: https://github.com/povedica/master-ia-lidr/pull/43
