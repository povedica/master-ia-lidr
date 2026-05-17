# Feature: Unified Jinja2 prompt templates (estimation v2 bundle)

## Objective

Move **all templatable LLM-facing text** into a versioned **Markdown + Jinja2** tree under `app/prompts/estimation/v2/`, so prompt specialists can edit prompts without touching Python string concatenation.

Python keeps **validation, orchestration, and context preparation** only. **`PromptRenderer` (or a thin `render_*` facade)** renders every artifact declared in `manifest.toml`.

This closes the partial migration from `feature-011`: today `render_estimation_user_message()` in `app/services/estimation_request_render.py` and mode fragments in `app/context/prompts/*.txt` remain outside Jinja. After this feature, **no production path** builds prompt prose in `.py` files.

**Why (prompt-specialist workflow):**

- One **canonical** filesystem location (`estimation/v2`) for review, diff, and rollback; `v1` stays available as a **synced copy** for callers that pin the older bundle label.
- Copy and layout changes do not require backend deploys of service logic (only template + context contract).
- `StrictUndefined` catches missing context keys in CI before incomplete prompts reach a model.
- Specialists work in Markdown they can read; engineers own the typed context dict, not section titles or bullet formatting.

## Context

**Current state**

| Artifact | Location today | Rendered by |
| --- | --- | --- |
| System + few-shot examples + JSON hint | `app/prompts/estimation/v1/*.j2` | `PromptRenderer` |
| User wrapper (`detail_level`, `output_format`) | `v1/user.j2` | Jinja |
| Guided form body (sections, attachments) | `app/services/estimation_request_render.py` | Python `parts.append(...)` |
| Adaptive mode instructions | `app/context/prompts/{mode}.txt` | `load_mode_prompt()` |
| Two-phase extraction system prompt | `EXTRACTION_SYSTEM_PROMPT` constant in `llm_service.py` | Hardcoded string |
| Assessment surface (guardrails / mode heuristics) | `render_estimation_assessment_surface()` | Python join |

**Consumers of guided / surface text:** `LLMPipeline`, `EstimationService.estimate_structured`, semantic cache vector surface, v1 routes, guardrails input phase.

**Existing infrastructure to extend:** `app/services/prompt_renderer.py`, `prompt_versions.py`, `prompt_context.py`, `estimation_prompt_rendering.py`, `PROMPT_ESTIMATION_VERSION` setting, golden tests in `tests/test_estimation_request_render.py` and `tests/test_prompt_renderer.py`.

**Related work items:** `feature-008` (guided form), `feature-011` (Jinja v1 bundle), `feature-012` (guarded pipeline). This feature does **not** change the public `EstimationResponse` / `EstimationResult` contracts unless a context key gap forces a schema note.

## Scope

### Includes

- New prompt bundle **`app/prompts/estimation/v2/`** with `manifest.toml` listing every template file (no hidden paths).
- Migrate **`render_estimation_user_message`** content to Markdown Jinja (e.g. `partials/guided_request.md.j2` or top-level `guided_request.j2`).
- Migrate **mode system fragments** from `app/context/prompts/*.txt` to Jinja partials under `v2/partials/modes/`.
- Migrate **two-phase extraction** system text to a versioned template.
- Migrate **inline cleaning** block (today `INLINE_CLEANING_BLOCK` in Python) to a partial when `preprocessing == inline_cleaning`.
- Unify **final user message** assembly in Jinja (guided body + detail/output preferences + optional preprocessing notes) so `v2/user.j2` is the single user prompt template, not a thin wrapper around Python Markdown.
- Extend **`PromptTemplateSet` / manifest** to declare optional templates: `guided_request_template`, `assessment_surface_template`, `mode_fragment_template` pattern, `preprocessing_templates`, etc.
- Extend **`build_estimation_prompt_context()`** (or `build_prompt_render_context()`) to expose a **stable, documented context schema** for specialists (field names, types, booleans for conditionals). Document the schema in `docs/technical/README.md`.
- Keep **`render_estimation_prompt()`** as the **only** public render entry for estimation LLM calls; add **`render_guided_user_message()`** / **`render_assessment_surface()`** that delegate to the same renderer + version selector.
- **Regression tests:** snapshot or golden files for **v2** renders; CI check that **`v1` bundle matches `v2`** (byte-identical templates or normalized render output on fixtures).
- **Default bundle `v2`:** runtime uses `estimation/v2` when `PROMPT_ESTIMATION_VERSION` is unset; update `DEFAULT_PROMPT_VERSIONS` in `prompt_versions.py` accordingly.
- **Retrocompatible `v1`:** after v2 is authoritative, **`app/prompts/estimation/v1/`** is populated as a **copy of v2** (same templates and manifest shape) so `PROMPT_ESTIMATION_VERSION=v1` keeps working without maintaining two divergent trees by hand.
- **Configurable bundle selection (phase 1):** `PROMPT_ESTIMATION_VERSION` environment variable (already wired as `Settings.prompt_estimation_version`).
- **Configurable bundle selection (future):** document extension point for non-env sources (e.g. per-tenant config, admin UI, request metadata); not implemented in this feature.
- Bump **`USER_MESSAGE_TEMPLATE_VERSION`** / prompt metadata to reflect `estimation/v2`.
- Update semantic cache bucket inputs to use the same rendered strings as the LLM path (no second formatting logic).

### Excludes

- Runtime prompt editor UI or database-backed prompt registry.
- Changing **`EstimationRequest`** JSON fields or OpenAPI shape (unless documenting new optional context-only derived fields).
- Replacing Instructor / LiteLLM / guardrail policy engine.
- i18n of template copy (templates stay **Spanish section titles** where required for mode heuristics unless a separate ADR changes that).
- Migrating **`app/context/examples/`** few-shot bodies to Jinja in this slice (may stay as data files included by `examples.j2`; optional follow-up).
- Per-tenant or dynamic prompt selection beyond env (reserved for a follow-up).
- Deleting the **`v1`** directory label (it remains as a retrocompatible alias copy of v2).

## Functional Requirements

### FR-01: Versioned v2 directory layout

```text
app/prompts/estimation/v2/
├── manifest.toml
├── system.j2
├── user.j2
├── examples.j2
└── partials/
    ├── guided_request.md.j2      # full guided form → Markdown body
    ├── assessment_surface.md.j2  # narrow text for guardrails + mode (no ## headers)
    ├── structured_output_hint.md.j2
    ├── modes/
    │   ├── basic.md.j2
    │   ├── standard.md.j2
    │   ├── professional.md.j2
    │   └── expert_review.md.j2
    └── preprocessing/
        ├── inline_cleaning.md.j2
        └── two_phase_extraction_system.md.j2
```

`manifest.toml` must list **every** template path the renderer may load. Unknown files are not loaded by convention.

### FR-02: Markdown as the authoring format

- All specialist-editable templates use **`.md.j2`** (or `.j2` with Markdown body).
- Output of render is **plain Markdown text** passed to the LLM (no HTML).
- Conditionals use Jinja (`{% if %}`, `{% for %}`); heavy business rules stay in Python **as context flags** (e.g. `has_attachments`, `attachment_notes: list[dict]`), not as Python string building.

### FR-03: Context-only Python boundary

`build_estimation_prompt_context()` (renamed or extended) must:

1. Accept `EstimationRequest` + resolved `EstimationMode` + preprocessing mode.
2. Decode attachments in Python; pass **structured lists** into templates (`attachment_notes`, never raw base64 in Jinja logic).
3. Resolve enum display strings and `other` free-text suffixes in Python **or** via small Jinja filters registered once on `PromptRenderer`.
4. Expose `guided_request_markdown` only if an intermediate render step is required; prefer **one user render** from `user.j2` that includes the guided partial.

Specialists must not need to import Python modules to edit prompts.

### FR-04: Single render entry points

| Function | Responsibility |
| --- | --- |
| `render_estimation_prompt(...)` | Returns `RenderedPrompt` (system + user) for LLM |
| `render_guided_user_message(request, *, version)` | Returns Markdown body (for tests, cache, guardrails) |
| `render_assessment_surface(request, *, version)` | Returns narrow surface string |

All call `PromptRenderer` with the same **resolved bundle version** from `resolve_prompt_bundle_version(settings)` (see FR-09).

### FR-05: Deprecate Python prose builders

- `estimation_request_render.py`: remove `parts.append` implementation; keep thin wrappers calling Jinja or delete module after re-exporting from `estimation_prompt_rendering.py`.
- `load_mode_prompt()`: delegate to Jinja partial for active version or remove when v1 retired.
- `EXTRACTION_SYSTEM_PROMPT` / `INLINE_CLEANING_BLOCK`: load from manifest-declared templates.

### FR-06: Parameter structure swappable later

Design the context dict as a **versioned contract** documented in `v2/context.schema.md` (or comments in `manifest.toml`):

- Template authors depend on **context keys**, not on `EstimationRequest` field names inside Jinja.
- A future refactor may rename API fields while keeping context keys stable, or bump `estimation/v3` with a mapping layer in Python only.

### FR-07: Metadata and observability

- `RenderedPrompt.prompt_version` must be `estimation/v2` when v2 is selected.
- `USER_MESSAGE_TEMPLATE_VERSION` becomes `guided-form-v2` (or aligned with bundle version).
- Langfuse / logs continue to record `prompt_version` and `examples_version`; no full prompt text in logs.

### FR-08: v1 as retrocompatible copy of v2

- **`v2` is the source of truth** for prompt edits; specialists change files under `app/prompts/estimation/v2/` only.
- **`v1` is not a legacy Python-string bundle** after this feature: it is a **directory-level copy** of `v2` (same file set, updated when v2 changes).
- Sync mechanism (pick one in implementation, document in README):
  - **Option A (recommended):** script `scripts/sync-estimation-prompt-v1-from-v2.sh` run in CI or pre-commit when `v2/` changes.
  - **Option B:** test that fails if `v1/` and `v2/` trees differ (forces explicit sync in PR).
- `manifest.toml` in `v1/` declares `version = "v1"` but template **content** matches `v2/`.
- Renders with `PROMPT_ESTIMATION_VERSION=v1` and unset env (default `v2`) must produce **identical** Markdown on golden fixtures.

### FR-09: Configurable prompt bundle version

**Phase 1 (this feature) — environment variable**

| Input | Behavior |
| --- | --- |
| `PROMPT_ESTIMATION_VERSION` unset or empty | Use **`v2`** (new default in `DEFAULT_PROMPT_VERSIONS["estimation"]`). |
| `PROMPT_ESTIMATION_VERSION=v2` | Explicit default; same as empty. |
| `PROMPT_ESTIMATION_VERSION=v1` | Load `app/prompts/estimation/v1/` (synced copy of v2). |
| Invalid / missing directory | Fail fast with `PromptVersionError` at render time (existing behavior). |

Implementation requirements:

- Centralize resolution in one function, e.g. `resolve_prompt_bundle_version(settings: Settings) -> str`, used by **all** render entry points, semantic cache bucket build, and `EstimationService.estimate_structured`.
- `Settings.prompt_estimation_version` maps from env `PROMPT_ESTIMATION_VERSION` (pydantic-settings); update field description to state default **`v2`** when empty.
- Log and expose `prompt_version` metadata as `estimation/{resolved}` (unchanged shape).

**Phase 2 (future, documented only)**

- Add a **`PromptBundleSelector`** (or settings hook) so bundle version can come from:
  - deployment config file,
  - per-tenant record,
  - authenticated admin override,
  - or optional request header — **without** changing template files.
- Env var remains the **fallback** when no higher-priority source is set.
- Do not implement Phase 2 in this feature; leave a short ADR note or comment in `prompt_versions.py` pointing to FR-09.

## Technical Approach

### Data flow (target)

```text
EstimationRequest (validated)
    → build_prompt_render_context()   # Python: types, attachments, flags
    → PromptRenderer.render(bundle, context)
        → partials/guided_request.md.j2
        → partials/modes/{mode}.md.j2
        → examples.j2 → system.j2
        → user.j2 (includes guided + preferences)
    → RenderedPrompt { system_prompt, user_prompt }
    → complete_structured() / guardrails / cache (unchanged orchestration)
```

### Code touchpoints

| Area | Change |
| --- | --- |
| `app/services/prompt_versions.py` | Extend `PromptTemplateSet` + manifest parsing for new template keys |
| `app/services/prompt_renderer.py` | Optional: render named partial; shared Jinja filters |
| `app/services/prompt_context.py` | Expand context; attachment decoding helpers |
| `app/services/estimation_prompt_rendering.py` | Wire v2 paths; public render helpers |
| `app/services/estimation_request_render.py` | Thin delegate or remove |
| `app/context/prompt_loader.py` | Deprecate in favor of Jinja modes |
| `app/services/llm_service.py` | Load extraction / cleaning templates by version |
| `app/guardrails/llm_pipeline.py` | Use `render_guided_user_message` / `render_assessment_surface` |
| `app/services/semantic_cache/*` | Same render functions for vector text |
| `tests/` | Golden files under `tests/fixtures/prompts/estimation/v2/` |
| `docs/technical/README.md` | Prompt bundle v2, context schema, specialist workflow |
| `.env.example` | `PROMPT_ESTIMATION_VERSION` — empty = **v2**; set `v1` only for retrocompat pin |
| `app/config.py` | Update `prompt_estimation_version` description; default empty → resolves to v2 |
| `app/services/prompt_versions.py` | `DEFAULT_PROMPT_VERSIONS["estimation"] = "v2"`; `resolve_prompt_bundle_version()` |
| `scripts/sync-estimation-prompt-v1-from-v2.sh` (optional) | Copy v2 → v1 for retrocompat |

### Settings

- **`PROMPT_ESTIMATION_VERSION`** — only selector in this feature; empty means **`v2`**.
- No new secrets.
- Future config sources: extension point per FR-09 Phase 2 (not env-only forever).

## Acceptance Criteria

- [x] `app/prompts/estimation/v2/` exists with complete `manifest.toml` and Markdown Jinja templates for guided body, modes, user, system, examples, preprocessing, and structured output hint.
- [x] No production code path concatenates guided-form Markdown or mode instructions in Python (except tests comparing parity).
- [x] `render_estimation_prompt()` produces identical structure to today on agreed golden fixtures when `version=v2` (parity test or approved diff).
- [x] `render_assessment_surface()` and `render_guided_user_message()` use the same v2 templates and version selector.
- [x] `StrictUndefined` fails tests when a required context key is removed.
- [x] Semantic cache bucket / vector text uses rendered strings from the same functions as the LLM path.
- [x] `docs/technical/README.md` documents context keys for prompt specialists and how to add a partial safely.
- [x] `DEFAULT_PROMPT_VERSIONS["estimation"]` is **`v2`**; empty `PROMPT_ESTIMATION_VERSION` resolves to v2 in all code paths.
- [x] `v1/` exists as a **copy of `v2/`** with `manifest.toml` version label `v1`; sync test or script documented.
- [x] Setting `PROMPT_ESTIMATION_VERSION=v1` renders the same output as default v2 on golden fixtures.
- [x] `resolve_prompt_bundle_version()` is the single resolution point (ready for future non-env config).

## Test Plan

### Unit tests

- `tests/test_prompt_renderer.py` — v2 partial renders, missing key raises `PromptRenderError`.
- `tests/test_estimation_prompt_rendering.py` — full `RenderedPrompt` for v2; metadata `estimation/v2`.
- `tests/test_estimation_request_render.py` — golden files for v2; **v1 ≡ v2** render parity on fixtures.
- `tests/test_prompt_bundle_version.py` (new) — empty env → `v2`; `v1` / `v2` explicit; invalid → error.
- `tests/test_prompt_versions.py` — manifest loads new template keys.
- Attachment decoding edge cases (PDF note-only, empty text file, unicode replacement) via context + template snapshot.

### Integration tests

- Mocked `POST /api/v2/estimate` succeeds with default (v2) and with `PROMPT_ESTIMATION_VERSION=v1`.
- Guardrail path receives assessment surface from template render (mock pipeline).

### Manual checks

1. `uv run python -c "..."` dump `system_prompt` / `user_prompt` for a full `EstimationRequest` fixture with `version=v2`.
2. Specialist review: edit one line in `guided_request.md.j2`, re-run dump script, confirm diff only in guided section.
3. One live estimate with default (v2) and one with `PROMPT_ESTIMATION_VERSION=v1` (optional, local only).

## Estimation

- Size: **L**
- Estimated time: **4–6 hours** (7 focused steps)
- Planned steps: **7**

## Implementation progress

- [x] Step 1: v2 bundle skeleton + `resolve_prompt_bundle_version()` + default `v2`
- [x] Step 2: Context builder + `guided_request.md.j2` + golden snapshots
- [x] Step 3: Mode partials + `system.j2` / examples wiring
- [x] Step 4: Unified `user.j2` + preprocessing partials; remove Python prose constants
- [x] Step 5: `assessment_surface.md.j2` + shared render helpers (guardrails, cache, LLM)
- [x] Step 6: Sync `v1/` from `v2/` + parity tests; thin delegates / deprecations
- [x] Step 7: Specialist docs (`docs/technical/README.md`, `.env.example`, optional `v2/README.md`)

**WIP PR:** https://github.com/povedica/master-ia-lidr/pull/12

## Baby steps (implementation order)

1. Add **`v2/`** tree + `manifest.toml` (canonical); port all templatable content from Python / legacy `v1` / `.txt` modes.
2. Implement `resolve_prompt_bundle_version()`; set **`DEFAULT_PROMPT_VERSIONS["estimation"] = "v2"`**; update `.env.example` and `config.py` descriptions.
3. Port `guided_request` to `partials/guided_request.md.j2`; context builder + v2 snapshots.
4. Port mode fragments to `partials/modes/*.md.j2`; wire `system.j2`.
5. Port `user.j2`, preprocessing partials; remove Python string constants from `llm_service.py`.
6. Add `assessment_surface.md.j2`; switch guardrails + cache to shared render helpers.
7. **Sync `v1/` from `v2/`** (script + test that trees match or renders are identical); adjust `v1/manifest.toml` version label only.
8. Deprecate `estimation_request_render.py` body (thin Jinja delegates); remove `load_mode_prompt` / `.txt` dependency for estimation path.
9. Document specialist workflow + FR-09 Phase 2 extension point in `docs/technical/README.md`.

## Documentation Plan

- `docs/technical/README.md` — prompt bundle v2 layout, render entry points, context schema for specialists, versioning.
- `docs/work-items/feature-011-jinja2-dynamic-prompt-rendering.md` — add cross-link note that v2 completes full templating (no edit required to close 011).
- `.env.example` — `PROMPT_ESTIMATION_VERSION` (empty = v2; `v1` = retrocompat pin).
- `README.md` — how to select bundle version today (env) vs future config.
- Optional: `app/prompts/estimation/v2/README.md` — short “how to edit templates” for non-developers (English, no secrets).

## Risks and mitigations

| Risk | Mitigation |
| --- | --- |
| Spanish `##` headers needed for heuristics change behavior | Parity tests on `assessment_surface`; document header rules in `v2/README.md` |
| Template edit breaks cache bucket | Bucket uses same render functions; bump cache schema version if output shape changes |
| Context schema drift vs `EstimationRequest` | Document `context.schema.md`; CI test that builds context from OpenAPI example fixture |
| Larger prompts from whitespace | Keep `trim_blocks` / `lstrip_blocks`; snapshot normalized whitespace in tests |
| `v1` and `v2` drift after edits | CI sync test or mandatory script in PR checklist when `v2/` changes |
| Operators expect empty env = v1 | Breaking change: document in README and `.env.example`; metadata `prompt_version` shows `estimation/v2` |

## Verification

- **Verified:**
  - `uv run pytest` — 236 passed (bundle resolution, renderer StrictUndefined, guided/assessment parity v1≡v2, tree sync test, estimation prompt rendering).
  - `scripts/sync-estimation-prompt-v1-from-v2.sh` copies `v2/` → `v1/` and sets manifest `version = "v1"`.
  - Default empty `PROMPT_ESTIMATION_VERSION` resolves to `v2` via `resolve_prompt_bundle_version()`.
- **Not verified:**
  - Live LLM estimate with default v2 and with `PROMPT_ESTIMATION_VERSION=v1` (manual, requires API keys).
  - Specialist dump script from Test Plan § Manual checks.
- **Residual risk:**
  - Breaking change for operators expecting empty env = v1; documented in `.env.example` and technical README.
  - Legacy `build_system_prompt()` still assembles examples in Python (no structured-output hint); v2 API uses full Jinja `system.j2`.
  - `app/context/prompts/*.txt` remain for `test_prompt_loader` only; estimation path uses Jinja mode partials.

## Repository commits (master-ia)

| Short hash | Message | Scope / summary |
| ---------- | ------- | --------------- |
| _pending_ | | |
