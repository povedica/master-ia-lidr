# Feature: Guided estimation form (replace free-form chat input)

## Objective

Replace the **free-form text** primary input in **estimador-cag** with a **guided form** so users supply only **business and project context** (product language). The backend maps that input to a **typed, validatable request object** and builds a **versioned server-side prompt** from a template. The **LLM provider wrapper and chain** (`build_provider_chain`, providers, `EstimationService` provider calls) stay unchanged; only **how user content is assembled** before the existing `estimate` / `stream_estimation` path changes.

## Context

- **Current API model:** `EstimateRequest` in `app/schemas/estimations.py` exposes `transcription` (required string), `preprocessing`, and `evaluate`. Routes call `EstimationService.estimate(body.transcription, ...)` and `stream_estimation(body.transcription, ...)` (`app/routers/estimations.py`).
- **Current demo UI:** `app/streamlit_app.py` uses a large `st.text_area` labeled “Transcription” plus preprocessing / evaluate / API URL—functionally a single open-ended box, not a product-level form.
- **Prompt composition today:** `EstimationService` in `app/services/llm_service.py` treats input as meeting-style text: guardrails (`check_estimation_domain`), adaptive mode (`assess_and_select_mode`), preprocessing (`inline_cleaning`, `two_phase`), then `build_system_prompt` + user payload. Constants `PROMPT_VERSION` and `EXAMPLES_VERSION` already support traceability when prompt assembly evolves.
- **Adaptive engine:** `app/services/estimation_engine.py` runs `assess_request` / `assess_and_select_mode` on the **same string** later passed as the user message. It uses English keyword signals (`_DETAIL_SIGNALS`, `_COMPLETENESS_SIGNALS`, `_AMBIGUITY_SIGNALS`), word counts, and ambiguity markers. Structured fields and the **rendered template** must not silently break those heuristics (see [Risks and mitigations](#risks-and-mitigations) and [Trade-off: assessment input surface](#trade-off-assessment-input-surface)).
- **Naming:** The codebase uses `EstimateRequest`, not `EstimationRequest`. This feature introduces a **structured inbound contract**; the implementation may name it `EstimationRequest` or extend `EstimateRequest` as long as one canonical Pydantic model represents the form payload at the HTTP boundary.

## Scope

### Includes

- **Streamlit:** Replace the primary “paste anything” experience with a **two-tier form** (primary fields + “More details” expander). Controls use **product language** (no “prompt”, “system message”, or model instructions). Technical options (`preprocessing`, `evaluate`) live in **Advanced** unless the demo explicitly needs them visible.
- **HTTP API:** Request bodies for `POST /api/v1/estimate` and `POST /api/v1/estimate/stream` accept the **structured object** (same shape as the form) instead of a raw conversational `transcription` string as the **primary** user content source.
- **Expanded field set:** Beyond the original minimal four dimensions (description, type, detail level, output format), include **scope lists**, **delivery**, **integrations**, **data sensitivity**, **constraints**, **risk**, and **optional attachments**—as specified in [Form structure and fields](#form-structure-and-fields).
- **Server mapping layer:** A dedicated module or functions (e.g. `app/services/estimation_request_render.py` or under `app/context/`) that render **versioned** Markdown/text from the structured fields for the **user message** passed into the existing service entry points. Bump or split `PROMPT_VERSION` (and document the mapping) when the template changes.
- **Enums / closed lists:** All selects use `StrEnum` (or equivalent) with **stable API literals** (logs, future cache keys, tests). See [Closed enums (API literals)](#closed-enums-api-literals).
- **Optional files:** Supplementary briefs with **documented limits** (max files, max total bytes, allowed MIME types) and **safe handling** (no secrets in logs; reject or strip unsupported types). Implementation may use **multipart uploads** or **base64-in-JSON**—pick one approach and document it in README/OpenAPI.
- **Tests:** Unit tests for schema validation, template rendering (deterministic output for fixed inputs), list length caps, and router/service integration with **mocked providers** (existing patterns in `tests/test_api.py`, `tests/test_llm_service.py`).
- **Docs:** README + technical docs: new request shape, field semantics, run commands (`uv run streamlit run ...`, `uv run pytest`), and migration note for anyone using raw `transcription` JSON today.

### Excludes

- Changing provider SDK usage, LiteLLM routing, or streaming event wire format beyond what is required to pass the new composed user text.
- Auth, persistence of uploads, virus scanning, or OCR for scanned PDFs (unless already present).
- A full redesign of evaluation (`evaluate`), stats logging, or adaptive mode logic—**unless** implementation explicitly wires `detail_level` / `output_format` into `assess_and_select_mode` (then document precedence in this spec’s [Trade-off: assessment input surface](#trade-off-assessment-input-surface)).
- i18n / multi-language UI copy beyond reasonable defaults (English UI strings align with repo technical-doc language; Spanish copy can be a follow-up).

---

## Form structure and fields

Design goal: **split the cognitive load**—closed choices and short lists carry **what** is being built and under **which constraints**; the long description carries **nuance** without repeating the same facts as prose. That improves estimates and keeps FR-006 (homogeneous composed payload) achievable.

### Recommended field groups

| Group | Purpose | Why it helps estimation |
|-------|---------|-------------------------|
| **Product context** | Who pays, for whom, measurable success | Fixes business horizon without “prompting”; reduces ambiguity the engine today infers from vague phrasing (“maybe”, “not sure”). |
| **Scope and outcomes** | What must exist when done | Replaces part of a wall-of-text transcription; supports stable breakdown (phases / line items). |
| **Delivery and time** | When and in what cadence | Surfaces `deadline` / `timeline`-like signals explicitly instead of burying them in paragraphs. |
| **Integrations and data** | Boundaries with external systems | Closed multi-select + short free names avoids integration laundry lists in prose. |
| **Constraints and quality** | Rules of the game | Compliance, hosting, languages: drives testing and hardening effort. |
| **Risk and uncertainty** | Unknowns stated upfront | Aligns with expert-review style outputs and explicit uncertainty sections. |
| **Output preferences** | Shape of the estimate | `detail_level` + `output_format`: template-driven, comparable across users. |
| **Attachments** | Point-in-time evidence | Briefs, requirement dumps; no persistence beyond the request. |

### A. Product context

| User-facing concept (label hint) | API field (suggested) | Type | Required | Validation / limits | Estimation value |
|----------------------------------|----------------------|------|----------|---------------------|------------------|
| Project name or code | `project_name` | Short text | No | max 120 chars, trim | Traceability in template/logs; low token cost. |
| One-line summary | `project_summary` | Short text | **Yes** | 20–200 chars after trim | Anchor for the rest of the narrative; replaces fuzzy “title” in a blob. |
| Project type | `project_type` | Select / pills | **Yes** | `ProjectType` enum | Routes expectations (mobile vs pipeline vs internal). |
| Target user or customer | `target_audience` | Select + optional short “other” | **Yes** | Enum or max 200 chars if free text | Clarifies UX priorities and scope. |
| Industry / domain | `industry` | Select + optional short “other” | No | Enum + max 80 chars if `other` | Regulatory and domain-complexity hints. |

### B. Scope and outcomes

| User-facing concept | API field | Type | Required | Validation / limits | Estimation value |
|---------------------|-----------|------|----------|---------------------|------------------|
| Project description | `project_description` | Multi-line | **Yes** | min **80–120** chars (implementation picks exact min), max aligned with token budget | Core narrative; should **reference** structured choices, not duplicate every select in prose. |
| Key deliverables | `deliverables` | List (bullets) | **Yes** | **3–8** items, max ~80 chars per item | Stable anchor for phases or line items. |
| Explicitly out of scope | `out_of_scope` | List | No | max **5** items, same per-item cap | Reduces fantasy scope and post-hoc arguments. |

### C. Delivery and time

| User-facing concept | API field | Type | Required | Validation / limits | Estimation value |
|---------------------|-----------|------|----------|---------------------|------------------|
| Urgency / milestone | `delivery_urgency` | Select | **Yes** | `DeliveryUrgency` enum | Replaces “ASAP” paragraphs; aligns buffer expectations. |
| Target date (if any) | `target_date` | ISO date or null | Conditional | Required when `delivery_urgency` is `fixed_date` or `critical` (exact rule in implementation); otherwise optional | Planning and staffing risk. |
| Delivery approach | `delivery_approach` | Select | No | `DeliveryApproach` enum | MVP vs single release vs phased roadmap. |

### D. Integrations and data

| User-facing concept | API field | Type | Required | Validation / limits | Estimation value |
|---------------------|-----------|------|----------|---------------------|------------------|
| Required integrations | `integration_categories` | Multi-select + optional short custom names | No | Enum set + max **3** custom strings ≤40 chars each | Connector and test effort without long prose. |
| Data sensitivity | `data_sensitivity` | Select | **Yes** | `DataSensitivity` enum | Security, logging, review depth. |

### E. Constraints and team

| User-facing concept | API field | Type | Required | Validation / limits | Estimation value |
|---------------------|-----------|------|----------|---------------------|------------------|
| Hosting / deployment constraints | `hosting_constraints` | Multi-select + optional short note | No | Enum + max **200** chars free text | Homogeneous “must use X” signals. |
| Team context | `team_context` | Select | No | `TeamContext` enum | Realism (client-only vs vendor-led vs mixed). |
| UI / content languages | `ui_languages` | Multi-select | No | max **3** values from enum | i18n and content effort. |

### F. Risk

| User-facing concept | API field | Type | Required | Validation / limits | Estimation value |
|---------------------|-----------|------|----------|---------------------|------------------|
| Perceived risk level | `risk_level` | Select / pills | No | `RiskLevel` enum | Triggers conservative ranges or caveats in output. |
| Critical external dependencies | `external_dependencies` | Short list | No | max **3** lines, ≤100 chars each | Vendors, approvals; supports expert-review tone. |

### G. Original spec dimensions (retain; UI wording)

| Field | API | Type | Required | Notes |
|-------|-----|------|----------|-------|
| Budget depth (not “prompt depth”) | `detail_level` | Select | **Yes** | UI label e.g. “Depth of estimate”; API values unchanged. |
| Output format | `output_format` | Select / pills | **Yes** | Drives structure of the estimate artifact. |
| Supporting documents | `attachments` | Files / list | No | Same as FR-005; strict size/type caps. |
| Input preprocessing | `preprocessing` | Select | Default `none` | Prefer **Advanced** in Streamlit for product demos. |
| Structure evaluation | `evaluate` | Boolean | Default `true` | Same; **Advanced** if UI is product-first. |

---

## Progressive disclosure

### Primary screen (suggested order)

1. `project_name` (optional)  
2. `project_summary` (required)  
3. `project_type`  
4. `target_audience`  
5. `project_description` (required)  
6. `deliverables` (required list)  
7. `delivery_urgency`  
8. `target_date` (shown when urgency implies a date; see validation rules in §B/C)  
9. `data_sensitivity`  
10. `detail_level`  
11. `output_format`  
12. `attachments`  
13. Submit  

Target cognitive load: roughly **eight decisions** plus two substantive texts (summary + description) and one structured list (deliverables), before optional expander.

### “More details” expander (optional but valuable)

- `out_of_scope`  
- `delivery_approach`  
- `integration_categories` (+ short custom names)  
- `hosting_constraints` (+ short note)  
- `industry`  
- `team_context`  
- `ui_languages`  
- `risk_level`  
- `external_dependencies`  
- `preprocessing`, `evaluate` (and API base URL if kept non-advanced)

---

## Closed enums (API literals)

Use Pydantic `StrEnum` (or `Literal` unions) with **stable** string values. UI labels are separate from these literals.

### `ProjectType` (`project_type`)

| Value | Notes |
|-------|--------|
| `web_saas` | |
| `web_marketing_site` | |
| `mobile_app` | |
| `internal_tool` | |
| `data_pipeline_etl` | Replaces a single generic `data_pipeline` if finer split is desired. |
| `api_platform` | |
| `desktop_app` | |
| `extension_plugin` | |
| `migration_modernization` | |
| `other` | Optional; **if present**, template must define behavior (e.g. ask model to infer subtype conservatively). |

### `Industry` (`industry`, optional)

`fintech`, `health`, `ecommerce`, `education`, `public_sector`, `industrial`, `generic_b2b`, `other`

### `DeliveryUrgency` (`delivery_urgency`)

`flexible`, `standard`, `fixed_date`, `critical`

### `DeliveryApproach` (`delivery_approach`, optional)

`mvp_then_iterate`, `single_release`, `phased_roadmap`, `unknown`

### `DataSensitivity` (`data_sensitivity`)

`public_only`, `internal_business`, `pii_light`, `pii_heavy`, `regulated_unknown`

### `IntegrationCategory` (`integration_categories`, multi)

`none`, `payments`, `crm`, `erp`, `identity_sso`, `email_notifications`, `file_storage`, `analytics_bi`, `maps_geo`, `messaging_chat`, `legacy_db`, `third_party_api_unknown`, `other`

If `none` is selected, implementation should treat as empty integration set (or validate mutual exclusivity with other values—document chosen rule).

### `HostingConstraint` (`hosting_constraints`, multi)

`no_preference`, `cloud_managed`, `customer_cloud_only`, `on_prem`, `air_gapped`, `hybrid`

### `TeamContext` (`team_context`, optional)

`client_only`, `vendor_led`, `mixed_team`, `unknown`

### `UiLanguage` (`ui_languages`, multi, max 3)

`en`, `es`, `pt`, `fr`, `de`, `other`

### `RiskLevel` (`risk_level`, optional)

`low`, `medium`, `high`, `unknown`

### `TargetAudience` (`target_audience` when not free-text)

`b2c_consumers`, `b2b_smb`, `b2b_enterprise`, `internal_employees`, `mixed`, `other`

### `DetailLevel` (`detail_level`)

`summary`, `medium`, `detailed`

### `OutputFormat` (`output_format`)

`phases_table`, `line_items`, `narrative`

---

## Evolution from the minimal v1 field list

| Original minimal spec | Recommendation |
|------------------------|------------------|
| Only long `project_description` | **Keep** as the narrative core but **narrow its role**: nuance and context, **not** repeating every select/list as prose. |
| Four `project_type` values | **Expand** to the `ProjectType` table above, or keep four literals + `other`; avoid forcing wrong classification. |
| `detail_level` | **Do not duplicate** in UI as “instructions to the model.” If later wired into `assess_and_select_mode`, document **precedence** vs inferred mode ([Trade-off](#trade-off-assessment-input-surface)). |
| `output_format` | **Keep**; orthogonal to adaptive mode selection. |
| `attachments` | **Keep**; clarify in docs that extracted text contributes to **token count** and possibly to **guardrails** if they run on the full rendered string. |

**Merge:** free-text deadlines inside `project_description` should largely move to **`delivery_urgency` + `target_date`**, with description only for exceptions.

---

## Risks and mitigations

### Prompt-like or meta-instruction fields

- **Avoid** additional open textareas such as “special instructions”, “tone”, or “role”—they invite meta-prompting and conflict with FR-001 / homogeneity goals.  
- **Avoid** long free-text “tech stack” where multi-select + one capped “other technical notes” line would suffice.  
- If a single exception field is required, cap length and name it in product language (e.g. “Known environment limitations”), not “Prompt”.

### Adaptive engine and template wording (`estimation_engine.py`)

The engine scores **detail**, **completeness**, and **ambiguity** using **English keyword lists** and **word counts** on the string passed into `assess_and_select_mode`. If the **rendered user message** injects many fixed English headers containing `_DETAIL_SIGNALS` terms (e.g. “API integrations”), metrics can be **artificially inflated** and **misalign** `EstimationMode` with true user intent.

**Mitigations (pick at implementation time; document the choice):**

- **A.** Use **Spanish or neutral** section titles in the template so boilerplate does not match English signal tokens; or  
- **B.** Run `assess_request` / mode selection on a **subset** of composed content (e.g. `project_summary` + `project_description` + user-origin lists only), **not** on full boilerplate; or  
- **C.** Short documented list of **forbidden** words in fixed headers.

### Ambiguity in user-entered text

If users still type “maybe”, “depends” heavily in `project_description`, ambiguity signals remain; **closed fields reduce** that when they replace vague prose.

### Tokens and cost

- Hard caps: **deliverables** count and chars per line, **out_of_scope** count, attachment count and total bytes, max length of `project_description`.  
- **Do not** duplicate the same facts in description and in every structured field—that multiplies tokens without benefit.

---

## Mapping: user message template vs future heuristics

| Source fields | Rendered user message (versioned Markdown template) | Heuristic / follow-up use |
|----------------|------------------------------------------------------|---------------------------|
| `project_summary`, `project_type`, `target_audience`, `industry` | “Context” section | `project_type` might later weight mode selection (v2); not required for v1. |
| `project_description` | “Project description” | Primary narrative for `assess_request` **if** implementation chooses subset assessment ([Trade-off](#trade-off-assessment-input-surface)). |
| `deliverables`, `out_of_scope` | “Scope” | Completeness-like signals if echoed in user-origin text. |
| `delivery_urgency`, `target_date`, `delivery_approach` | “Delivery” | Reinforces deadline/timeline signals; avoid duplicating the same facts in both template and a redundant sentence in `project_description`. |
| `integration_categories`, `data_sensitivity`, `hosting_constraints`, `team_context`, `ui_languages` | “Constraints and environment” | Prefer stable, short rendering; watch English signal leakage. |
| `risk_level`, `external_dependencies` | “Risks” | Supports conservative ranges and expert-review tone. |
| `detail_level`, `output_format` | “Preferences” (or footer block) | Template wording; optional future link to `select_mode` with explicit precedence. |
| `attachments` | “Supporting documents” | Extracted text adds words and signals; enforce limits. |
| `preprocessing`, `evaluate` | **Not** part of user message; remain JSON fields only | Unchanged provider boundary. |

---

## Trade-off: assessment input surface

Today **`assess_and_select_mode(transcription)`** runs on the **same** string that becomes (or feeds) the user content for the LLM. Structured fields **improve** comparability and product UX, but a **verbose English template** can distort keyword-based heuristics.

**Implementation must document one of:**

1. **Full rendered string** for both assessment and LLM (simplest path; mitigate with section titles per [Risks](#risks-and-mitigations)), or  
2. **Subset string** for assessment (user narrative + structured bullets only) and **full rendered string** for the LLM (two compositions; more code, clearer metrics), or  
3. **Explicit coupling** of `detail_level` / `output_format` into mode selection with **precedence rules** over inferred mode (larger behavioral change—flag as optional follow-up).

**Residual risk:** If `detail_level` and `EstimationMode` disagree without documented precedence, users get confusing depth (template says “detailed”, engine chose `STANDARD`).

---

## Functional Requirements

### FR-001: Project description

- Required multi-line field: nuance, context, constraints **without** repeating structured lists verbatim.
- Validated non-empty after trim; **minimum** length in the **80–120** character range (exact value fixed in implementation); max length documented for token budget.

### FR-002: Project summary

- Required one-line summary (`project_summary`), 20–200 characters after trim.

### FR-003: Project type

- Required `ProjectType` enum (full set in [Closed enums](#closed-enums-api-literals)).

### FR-004: Target audience

- Required: `TargetAudience` enum **or** capped free text (max 200 chars)—product decision; API should remain JSON-friendly (prefer enum + optional `target_audience_other`).

### FR-005: Detail level

- Required `DetailLevel`: `summary` | `medium` | `detailed`—drives **server template** wording, not user-authored “prompt”.

### FR-006: Output format

- Required `OutputFormat`: `phases_table` | `line_items` | `narrative`.

### FR-007: Deliverables

- Required list of **3–8** non-empty strings; per-item max length ~80 characters (exact cap in implementation).

### FR-008: Delivery and data

- Required `delivery_urgency`; required `data_sensitivity`.  
- `target_date` conditional validation when urgency implies a calendar constraint (`fixed_date` / `critical`—exact rule in implementation).

### FR-009: Supporting files

- Optional `attachments`; empty list allowed. Documented max file count, total bytes, and MIME allowlist; safe logging (no raw secrets).

### FR-010: Optional structured fields

- Optional fields per [Form structure and fields](#form-structure-and-fields): `project_name`, `industry`, `out_of_scope`, `delivery_approach`, `integration_categories` (+ short customs), `hosting_constraints`, `team_context`, `ui_languages`, `risk_level`, `external_dependencies`—each with the caps listed above.

### FR-011: Homogeneous quality

- Identical structured payload + normalized attachment text → **identical** composed user message bytes (FR-006 from original spec).

### FR-012: Legacy removal

- Public API **no longer** accepts `transcription` as the primary contract; `dev-tools/stress_api.py` and tests migrate to structured JSON. Default **clean break** unless a one-release internal deprecation is explicitly approved.

### FR-013: Advanced options

- `preprocessing` and `evaluate` remain on the request model; UI may hide under Advanced.

---

## Technical Approach

### Request schema (HTTP)

Introduce a Pydantic model (working name **`EstimationRequest`**) including at minimum:

| Field | Type |
|-------|------|
| `project_name` | `str \| None` |
| `project_summary` | `str` |
| `project_type` | `ProjectType` |
| `target_audience` | `TargetAudience` or `str` (see FR-004) |
| `industry` | `Industry \| None` (+ optional `industry_other`) |
| `project_description` | `str` |
| `deliverables` | `list[str]` (constrained length) |
| `out_of_scope` | `list[str] \| None` |
| `delivery_urgency` | `DeliveryUrgency` |
| `target_date` | `date \| None` |
| `delivery_approach` | `DeliveryApproach \| None` |
| `integration_categories` | `list[IntegrationCategory]` (optional empty) |
| `integration_custom_names` | `list[str]` (optional, capped count and length) |
| `data_sensitivity` | `DataSensitivity` |
| `hosting_constraints` | `list[HostingConstraint]` (optional) |
| `hosting_notes` | `str \| None` (capped) |
| `team_context` | `TeamContext \| None` |
| `ui_languages` | `list[UiLanguage]` (max 3) |
| `risk_level` | `RiskLevel \| None` |
| `external_dependencies` | `list[str] \| None` (capped) |
| `detail_level` | `DetailLevel` |
| `output_format` | `OutputFormat` |
| `attachments` | `list[Attachment]` (optional) |
| `preprocessing` | `str` (same allowed set as today) |
| `evaluate` | `bool` |

Replace router usage of `EstimateRequest.transcription` with this model (rename in place or new type + router update).

### Composition layer

- `render_estimation_user_message(request: EstimationRequest) -> str` builds the string passed to `EstimationService.estimate(...)` / `stream_estimation(...)`.
- Markdown sections aligned with [Mapping](#mapping-user-message-template-vs-future-heuristics).
- Bump `PROMPT_VERSION` or add `USER_PROMPT_TEMPLATE_VERSION`; surface in existing `prompt_version` / logging where applicable.

### Domain guardrails

- Run `check_estimation_domain` on the chosen **assessment surface** (see [Trade-off](#trade-off-assessment-input-surface)). Prefer one documented code path.

### Streamlit

- Primary + “More details” layout; `st.file_uploader` for attachments; same SSE client path, new JSON body.

### Provider boundary

- **No changes** to provider invocation beyond the composed user text from `_prepare_call`.

---

## Acceptance Criteria

- [x] User can complete an estimate **without** free-form model instructions; long free text is limited to **product description** roles (`project_summary`, `project_description`, capped notes).
- [x] `POST /api/v1/estimate` and `POST /api/v1/estimate/stream` accept **only** the structured request (no `transcription`-only public contract).
- [x] OpenAPI describes all enums and constraints (list sizes, string lengths) via Pydantic `Field` / validators on `EstimationRequest`.
- [x] Server builds the LLM user message from a **versioned template** (`USER_MESSAGE_TEMPLATE_VERSION` / `PROMPT_VERSION` bump); template changes bump version metadata.
- [x] Streamlit mirrors API fields with primary vs advanced disclosure.
- [x] Tests cover validators, render assertions, attachment rejection, and API fakes.

---

## Test Plan

- **Unit:** Per-field validators; deliverable count; conditional `target_date`; `render_estimation_user_message` deterministic golden file.
- **Integration:** `TestClient` structured POSTs for estimate + stream with mocked service.
- **Manual:** `uv run uvicorn` + `uv run streamlit run app/streamlit_app.py`; submit primary + advanced paths; small `.txt` attachment.

---

## Documentation Plan

- `proyectos/estimador-cag/README.md`: example JSON body, field semantics, migration from `transcription`.
- `proyectos/estimador-cag/docs/technical/README.md`: assessment-surface decision and attachment limits.
- `.env.example` + `Settings` if new limits are configurable.
- Second Brain mirror: `bash scripts/sync-estimador-cag-docs.sh` when vault copy exists.

---

## Baby Steps (implementation order)

1. StrEnums + `EstimationRequest` with all validators and unit tests (including list caps).
2. `render_estimation_user_message` + template + version bump; golden tests; **document assessment input** choice.
3. Routers → render → `estimate` / `stream_estimation`; update API tests and `stress_api.py`.
4. Streamlit: primary form + expander + uploads; manual smoke.
5. README / technical docs; `uv run pytest`.

---

## Implementation progress

- [x] **Git branch:** `feature/estimador-cag-008-guided-form` (work continues here until merge).
- [x] Schemas + validators + unit tests (`EstimationRequest`, `Attachment`).
- [x] `render_estimation_user_message` / `render_estimation_assessment_surface` + `assessment_input` wiring in `EstimationService`.
- [x] Routers, `stress_api`, API tests, `PROMPT_VERSION` → `v7-guided-input`.
- [x] Streamlit guided form + expander + optional uploads.
- [x] README + `docs/technical/README.md` (assessment surface, attachments, curl samples).
- [ ] **Manual smoke:** FastAPI + Streamlit end-to-end with a small `.txt` attachment (not executed in this session).

## Verification

- `cd proyectos/estimador-cag && uv run pytest` — **148 passed** (automated, this session).
- Manual: FastAPI + Streamlit as above.

**Verified / not verified / residual risk:** Automated suite verified. Manual Streamlit + attachment path **not** verified here. Residual: `detail_level` vs inferred `EstimationMode` precedence remains unchanged (explicit coupling still optional follow-up).

---

## Repository commits (master-ia)

| Short hash | Message | Scope / summary |
|------------|---------|-----------------|
| `a1f3aa3` | `chore(cursor): add product-strategy-analyst agent and output folder` | Adds the Cursor agent definition and `docs/agent_outputs/product-strategy-analyst/README.md` for output naming conventions. |
| `a362d75` | `docs(estimador-cag): add feature-008 guided estimation form work item` | Canonical work item: guided form spec, enums, risks, API mapping, acceptance criteria, and verification notes. |
| `f8540b4` | `feat(estimador-cag): guided EstimationRequest form and render pipeline` | `EstimationRequest`, render module, `assessment_input`, routers, Streamlit, tests, README and technical docs. |

_Add further rows only if the work splits across additional commits._
