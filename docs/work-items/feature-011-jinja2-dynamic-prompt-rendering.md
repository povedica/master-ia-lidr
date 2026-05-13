# Feature: Jinja2 Dynamic Prompts and Pydantic-First Structured Estimation Output

## Objective

Deliver two capabilities as one coherent feature:

1. **Versioned Jinja2 prompts** rendered from the typed inbound `EstimationRequest` (`POST /api/v1/estimate` and `POST /api/v1/estimate/stream`).
2. **Structured, typed estimation output** so the LLM behaves like a function with a fixed return type: the API returns a validated Pydantic object (not free-form Markdown for clients to parse).

The canonical data flow:

**`EstimationRequest` (inbound) → normalization / prompt context → Jinja2 render → LLM call under JSON Schema derived from Pydantic → parse / validate → `EstimationResult` (domain) inside `EstimationResponse` (transport) → client.**

This combines:

- **Prompt as software artifact:** versioned templates, testable rendering, `StrictUndefined`.
- **Schema as contract:** the **output Pydantic model is the single source of truth**; JSON Schema for the provider is **auto-generated** from that model (`model_json_schema()` or equivalent), never maintained as a parallel hand-written artifact.

The endpoint stays an orchestrator: parse request, build context, render prompts, call the structured-output adapter, assemble typed response. No Markdown regex pipelines for the primary client payload.

## Context

**Difference from the earlier spec revision:** the scope is no longer “Jinja2 only with a future hint for JSON”. Structured output is **in scope**: the default success path returns a **typed JSON body** validated in Python. Presentation is decoupled from the AI service: the UI renders tables, narrative, or summaries from **structured fields**, not from parsing generated prose.

**Current codebase (baseline to replace or migrate):**

- `app/schemas/estimation_request.py` — inbound guided form (`EstimationRequest`).
- `app/schemas/estimations.py` — `EstimateResponse` with `estimation: str` plus regex-oriented `structure_evaluation` / `output_validation` driven by Markdown heuristics.
- `app/routers/estimations.py` — builds user message + assessment surface, calls `EstimationService.estimate(...)`.
- `app/services/estimation_request_render.py` — deterministic Markdown user message.
- `app/services/llm_service.py` — composes system prompt from static files + examples; returns text; defines an internal dataclass also named `EstimationResult` (execution outcome: text + metadata). **Naming collision:** this feature’s **domain** output model should live under `app/schemas/` as the public **`EstimationResult`**; the existing service-internal dataclass **must be renamed** (for example `LlmEstimationCallOutcome` or `ProviderEstimationPayload`) so “`EstimationResult`” means one thing in the API contract.
- `app/services/evaluation.py` — `evaluate_estimation_structure` on Markdown; **must not remain the primary quality gate** for the new contract. Replace or narrow to optional legacy/dev tooling, or reimplement checks as **Pydantic validators** on the structured model (totals, ranges, cross-field consistency).

**Provider stack alignment (recommended default):**

- **LiteLLM** — already used for routing models/providers; keep business logic agnostic of OpenAI vs Anthropic vs other routes.
- **Instructor** — recommended **Pydantic-first** layer on top of the chat completion path: `response_model=...`, retries/validation hooks, hiding provider differences for structured outputs where supported.

Routes must not branch on “OpenAI vs Anthropic” for the core estimate; a single **structured completion port** (Instructor + LiteLLM-backed client) owns that.

## Open questions

- **`/estimate/stream`:** structured output is often a **single final JSON object**, not token-by-token partial JSON. Decide one: (a) keep SSE but emit one structured `done` payload after full validation, (b) deprecate streaming for structured estimates until a supported incremental protocol exists, or (c) stream only **non-primary** events (progress) and structured body once. Document the chosen behavior in the implementation PR.
- **Backward compatibility:** whether to version the HTTP response (`/api/v2/estimate`) or break `EstimateResponse` in place; default recommendation: explicit **v2 route** or response discriminator during transition so the web client can migrate cleanly.

## Motivation

The current prompt composition is hard to evolve because prompt structure, request-field formatting, examples injection, preprocessing instructions, and mode-specific behavior are spread across Python string concatenation.

Problems with the current static/manual approach:

- Prompt changes require editing Python code, which makes product/prompt-engineering review harder.
- Missing fields or renamed context keys can render silently if not guarded.
- Dynamic behavior such as `detail_level`, `output_format`, attachments, hosting constraints, UI languages, or preprocessing modes is harder to test in isolation.
- Prompt versions are labels, not first-class directories with rollback-ready artifacts.
- The API returns **free-form Markdown** (`estimation: str`), which pushes the frontend toward fragile parsing or prose-only views.
- **Regex / Markdown structural checks** are not a stable contract for machine-consumed data; correctness should be enforced by **schema + Pydantic validation**, with **early explicit errors** when the model violates the contract.

The desired state:

- **Prompts:** versioned Jinja2, one render entry point, `StrictUndefined`, testable artifacts.
- **Output:** **Pydantic model → auto-generated JSON Schema → LLM under contract → validated `EstimationResult`**; the frontend renders **typed fields** without intermediate text parsers.
- **Separation:** the AI service returns a **rich stable shape**; `output_format` on the request only **steers prompt instructions and emphasis**, not an alternate ad-hoc JSON shape for the same endpoint.

## Scope

### Includes

- Add `Jinja2` as a runtime dependency using `uv add jinja2`.
- Add **Instructor** as the recommended typed structured-output layer: `uv add instructor`.
- Keep **LiteLLM** for provider/model routing; use a **single Pydantic-first structured completion adapter** (Instructor over LiteLLM) so OpenAI / Anthropic / aggregators do not fork estimator business logic.
- Introduce versioned prompt directories for the estimation use case.
- Add a prompt context builder that maps `EstimationRequest` into a Jinja2-safe context.
- Add a prompt template loader using `FileSystemLoader`.
- Add a renderer using `StrictUndefined`, `trim_blocks=True`, and `lstrip_blocks=True`.
- Add a prompt version selector with a default active version.
- Render both system and user prompts through one Python entry point.
- Keep request normalization and business rules in Python, not in templates.
- Add focused tests for context building, conditional rendering, version selection, prompt regression, **output schema derivation**, **Pydantic validators**, and **structured-call retries** (mocked providers).
- Update docs to describe prompt artifacts, **dual API contracts**, schema versioning, Instructor + LiteLLM, and **frontend rendering from structured data** (no prose parsing).
- Define **`EstimationResult`** (domain) and **`EstimationResponse`** (transport); evolve `POST /api/v1/estimate` to return **`result` as a validated object**, not a Markdown string.
- **JSON Schema** for the LLM must be **derived only** from the output Pydantic model; validate responses back into **`EstimationResult`** instances.
- **Bounded retries** when the model output fails structural or business validation.

### Excludes

- No redesign of the public `EstimationRequest` schema unless a blocking gap appears during implementation.
- No **hand-maintained** JSON Schema that duplicates the Pydantic output model.
- No **client-facing** primary path that regex-parses Markdown or free text to build `EstimationResult`.
- No migration to LangChain, LangGraph, DSPy, or another prompt framework as the core abstraction (Instructor + LiteLLM remains the default stack).
- No runtime prompt editing UI.
- No database-backed prompt registry.

## Functional Requirements

### FR-01: Versioned prompt artifacts

Prompts must live as versioned files outside service logic:

```text
app/
├── prompts/
│   └── estimation/
│       ├── v1/
│       │   ├── manifest.toml
│       │   ├── system.j2
│       │   ├── user.j2
│       │   ├── examples.j2
│       │   └── partials/
│       │       ├── output_contract.md.j2
│       │       ├── request_context.md.j2
│       │       └── structured_output_hint.md.j2
│       └── v2/
│           └── ...
```

Default recommendation: use `app/prompts/estimation/<version>/` instead of `app/context/prompts/` because templates are executable prompt artifacts, not only static CAG context. Keep historical examples under `app/context/examples/` unless this feature intentionally migrates them later.

### FR-02: Single prompt rendering entry point

Application code must render prompts through one public function:

```python
def render_estimation_prompt(
    request: EstimationRequest,
    *,
    mode: EstimationMode,
    examples: Sequence[EstimationExample],
    version: str | None = None,
) -> RenderedPrompt:
    ...
```

The rest of the backend should not call Jinja2 directly.

### FR-03: Strict template failures

The renderer must use `StrictUndefined` so missing context keys fail fast during tests and runtime instead of producing incomplete prompts.

Template rendering errors must be converted into a safe internal error at the service boundary. Logs may include prompt use case, version, and template name, but must not include full user-provided prompt content or secrets.

### FR-04: Clean endpoint orchestration

The router should orchestrate only:

```python
assessment_surface = render_estimation_assessment_surface(body)
result = await service.estimate_structured(body, assessment_surface=assessment_surface)
```

Prompt rendering and structured LLM calls live inside **`EstimationService`** (or a dedicated use-case function it calls). The router must not call Jinja2, Instructor, or raw provider SDKs.

After this feature, the route returns **`EstimationResponse`** (or a forward-compatible v2 route) with a validated **`result: EstimationResult`**.

### FR-05: Dynamic rendering from request parameters

The templates must adapt to these fields through prepared context flags, not heavy template logic:

- `detail_level`
- `output_format`
- `attachments`
- `integration_categories`
- `hosting_constraints`
- `ui_languages`
- `delivery_urgency` / `target_date`
- `preprocessing`

### FR-06: Prompt metadata

Rendered prompts must carry metadata:

```python
@dataclass(frozen=True)
class RenderedPrompt:
    system_prompt: str
    user_prompt: str
    prompt_version: str
    examples_version: str
    template_names: tuple[str, ...]
```

This prepares the existing metadata path (`prompt_version`, `examples_version`) to reflect actual selected artifacts.

### FR-07: Dual contracts — inbound vs outbound

The API must treat **two separate Pydantic contracts**:

| Contract | Model (recommended module) | Role |
|----------|----------------------------|------|
| **Inbound** | `EstimationRequest` (`app/schemas/estimation_request.py`) | Client → server: guided form, enums, attachments. |
| **Domain outbound** | `EstimationResult` (`app/schemas/estimation_result.py`) | **Single source of truth** for what the model must produce and what the UI consumes: nested objects, numbers, lists. |
| **Transport outbound** | `EstimationResponse` (`app/schemas/estimation_response.py` or extend `app/schemas/estimations.py`) | HTTP envelope: `result`, `prompt_version`, `examples_version`, optional `usage`, `assessment`, `evaluate`-driven diagnostics, `request_id`, etc. |

Connection rule: **`EstimationRequest` fields drive Jinja context only**; **`EstimationResult` shape is independent of presentation** and stable across providers. `output_format` may add **prompt instructions** and optional **UI hints** inside `EstimationResult` (e.g. `presentation: { "primary_view": "phases_table" }`) but **must not** introduce alternate top-level response shapes per format.

### FR-08: Pydantic-first pipeline (no hand-written schema fork)

The only allowed contract flow for the primary estimate path:

```text
EstimationResult (Pydantic model)
    → JSON Schema (auto-generated, e.g. model_json_schema())
    → LLM call constrained to that schema (via Instructor / provider structured mode)
    → raw JSON / object from provider
    → EstimationResult.model_validate(...)  # structural + business validators
    → EstimationResponse(result=..., ...)
```

Forbidden as the **primary** path: maintaining a duplicate `.json` schema file that can drift from `EstimationResult`; parsing Markdown tables with regex to populate domain objects.

### FR-09: LLM as typed function

The estimation call must behave like **`complete(...) -> EstimationResult`**: fixed return type, validation errors surface as **explicit, early failures** (after bounded retries), not as silent partial strings.

### FR-10: Structured-output integration (recommended default)

- Use **Instructor** with `response_model=EstimationResult` (or equivalent API) on a **LiteLLM-backed** chat client.
- Centralize creation of the Instructor client / patched completion in one module, e.g. `app/services/structured_llm_client.py`.
- Provider-specific details (**OpenAI** `response_format` / structured outputs, **Anthropic** tool-use / forced tool schema, **other** via LiteLLM) stay **inside** that adapter, not in routers or prompt builders.

Document briefly the three underlying mechanisms (for operators, not for branching business code):

1. **OpenAI:** native structured outputs / JSON schema `response_format` where available.
2. **Anthropic:** constrained tool use returning JSON matching schema.
3. **Other / aggregator:** LiteLLM unified parameters where supported; Instructor normalizes validation failures.

**Default product decision:** one estimator-facing function, e.g. `complete_structured(system, user, *, response_model: type[EstimationResult], ...) -> EstimationResult`, implemented with Instructor + LiteLLM.

### FR-11: Business coherence validators

`EstimationResult` must include **`model_validator` / `field_validator`** rules beyond JSON shape, for example:

- `sum(line_item.hours) ≈ total_hours` within tolerance, or exact equality if the schema mandates line items always present.
- `total_cost_eur` consistent with line items when both are required.
- `confidence` in `[0, 1]` or allowed enum.
- `duration_weeks` > 0; hours ≥ 0.
- Cross-check `phases` vs `line_items` when both populated.

Validators are **unit-tested** with valid and invalid fixture payloads.

### FR-12: Errors and retries

When the model returns JSON that fails Pydantic validation or Instructor raises:

- Retry up to **`N`** times (configurable, e.g. `STRUCTURED_OUTPUT_MAX_ATTEMPTS`, default 2–3) with identical or tightened system instructions (“fix JSON to match schema”).
- Log **error type**, attempt index, `prompt_version`, provider name — **never** raw API keys or full prompts containing secrets.
- If all attempts fail: return **`503`** or **`422`** with a safe, non-leaky message (choose policy: `422` if treated as unprocessable model output, `503` if upstream failure); document the choice in implementation.

### FR-13: Frontend consumption

The **`web/`** client (and any API consumer) must treat **`EstimationResponse.result`** as the **primary** source for estimation UI: tables, lists, narrative layout from **typed fields**. Optional: a **non-primary** `human_summary: str | None` field on `EstimationResult` for accessibility is allowed, but **must not** be the only machine-readable payload.

### FR-14: `evaluate` flag

If `evaluate=true` remains, diagnostics must operate on **`EstimationResult`** (validator pass/fail, optional secondary quality checks), **not** on Markdown regex scoring as the gate for “valid estimate”. Legacy `structure_evaluation` may be removed or replaced with **schema-aware** checks (e.g. optional `EstimationQualityReport` model).

## Dual contracts and flow (normative)

```text
POST /api/v1/estimate (EstimationRequest JSON)
  → Pydantic parse / validate inbound contract
  → build assessment_surface (unchanged guardrail / mode inputs)
  → EstimationService: domain guardrail + EstimationMode selection
  → build_estimation_prompt_context(...) + render_estimation_prompt(...)  [Jinja2]
  → derive JSON Schema from EstimationResult.model_json_schema()
  → complete_structured(system, user, response_model=EstimationResult)  [Instructor + LiteLLM]
  → EstimationResult.model_validate / Instructor validation
  → (optional bounded retries on validation failure)
  → EstimationResponse(result=..., prompt_version=..., ...)
```

## Technical Approach

### Proposed architecture

```text
POST /api/v1/estimate
  -> FastAPI parses EstimationRequest
  -> router builds assessment_surface only
  -> EstimationService validates domain and selects EstimationMode
  -> EstimationPromptContextBuilder maps request + mode + examples to context
  -> PromptVersionSelector resolves estimation/v1
  -> PromptTemplateLoader returns Jinja templates from filesystem
  -> PromptRenderer renders system.j2, examples.j2, user.j2 with StrictUndefined
  -> StructuredLlmClient (Instructor + LiteLLM) completes with response_model=EstimationResult
  -> EstimationResponse assembled with result + prompt_version + metadata
```

Default recommendation: render prompts inside `EstimationService._prepare_call()` after `mode` is known and after two-phase preprocessing, because the prompt depends on adaptive mode, examples, preprocessing, and final user text.

### Modules to create

```text
app/
├── prompts/
│   └── estimation/
│       └── v1/
│           ├── manifest.toml
│           ├── system.j2
│           ├── user.j2
│           ├── examples.j2
│           └── partials/
├── services/
│   ├── prompt_context.py
│   ├── prompt_renderer.py
│   ├── prompt_versions.py
│   └── structured_llm_client.py    # Instructor + LiteLLM; single structured completion port
└── schemas/
    ├── estimation_result.py        # domain EstimationResult (nested models)
    ├── estimation_response.py      # transport EstimationResponse(result=..., metadata)
    └── prompt_rendering.py         # optional: RenderedPrompt if not a dataclass-only module
```

Recommended responsibilities:

- `app/services/prompt_context.py`: map `EstimationRequest`, `EstimationMode`, examples, and preprocessing state into a serializable context object.
- `app/services/prompt_versions.py`: resolve active prompt version per use case (`estimation`) and validate directory availability.
- `app/services/prompt_renderer.py`: own Jinja2 environment creation, template loading, strict rendering, and `RenderedPrompt`.
- `app/services/structured_llm_client.py`: own Instructor client wiring, LiteLLM model id from `Settings`, `complete_structured(..., response_model=EstimationResult)`, retries, and provider-specific quirks **only here**.
- `app/schemas/estimation_result.py`: **domain** `EstimationResult` — the only schema source for JSON Schema generation and validation.
- `app/schemas/estimation_response.py`: **transport** `EstimationResponse` wrapping `result` plus `prompt_version`, usage, assessment, etc.
- `app/prompts/estimation/v1/*.j2`: hold prompt content only; instruct the model to output JSON matching the **auto-derived** schema (by reference in prompt text: schema version id / field names), not hand-copied full schema dumps unless needed for debugging (prefer short “match server contract EstimationResult v1” wording).

**Naming migration (required):** rename the existing service-internal dataclass `EstimationResult` in `app/services/llm_service.py` (text + metadata) to a non-conflicting name so **`app.schemas.estimation_result.EstimationResult`** becomes the public domain model without import ambiguity.

Avoid putting mapping logic inside `app/context/` because that package currently represents CAG examples/static context, while this feature introduces executable rendering infrastructure.

### Dependency

Add:

```bash
uv add jinja2 instructor
```

`litellm` is already a project dependency; structured calls should use it from `structured_llm_client.py` rather than adding parallel raw SDK paths in routes.

No additional dependency is required for `manifest.toml` if the file uses TOML and Python 3.11 `tomllib` reads it.

Optional settings to document in `.env.example` when implemented:

- `STRUCTURED_OUTPUT_MAX_ATTEMPTS` (integer, default 2–3).
- `PROMPT_ESTIMATION_VERSION` (optional override).
- `ESTIMATION_RESULT_SCHEMA_VERSION` or bump `EstimationResult` model version in code when breaking domain shape (prefer **model versioning** + migration notes over silent field drift).

## Directory Structure

Recommended `v1` layout:

```text
app/prompts/estimation/v1/
├── manifest.toml
├── system.j2
├── user.j2
├── examples.j2
└── partials/
    ├── estimation_modes.md.j2
    ├── output_contract.md.j2
    ├── request_context.md.j2
    └── structured_output_hint.md.j2
```

Example `manifest.toml`:

```toml
use_case = "estimation"
version = "v1"
description = "Guided-form estimation prompt rendered from EstimationRequest."
system_template = "system.j2"
user_template = "user.j2"
examples_template = "examples.j2"
structured_outputs_ready = true
```

Recommended default selector behavior:

- `estimation` defaults to `v1`.
- A future `PROMPT_ESTIMATION_VERSION=v2` setting may override the default.
- Invalid versions fail at startup or first render with a clear configuration error.
- Rollback means changing the selected version back to a previous directory, with no code change if the renderer contract remains compatible.

## Components

### `PromptVersionSelector`

Purpose: resolve the directory and metadata for a prompt use case/version.

```python
@dataclass(frozen=True)
class PromptTemplateSet:
    use_case: str
    version: str
    root: Path
    system_template: str
    user_template: str
    examples_template: str
```

Recommended API:

```python
def resolve_prompt_template_set(
    use_case: str,
    requested_version: str | None = None,
) -> PromptTemplateSet:
    ...
```

Default version can initially be a module constant:

```python
DEFAULT_PROMPT_VERSIONS = {"estimation": "v1"}
```

If environment configuration is added, update `.env.example`, `README.md`, and `docs/technical/README.md`.

### `EstimationPromptContextBuilder`

Purpose: keep all business mapping and normalization in Python.

Recommended API:

```python
def build_estimation_prompt_context(
    request: EstimationRequest,
    *,
    mode: EstimationMode,
    examples: Sequence[EstimationExample],
    rendered_user_text: str | None = None,
    preprocessing: str,
) -> dict[str, Any]:
    ...
```

`rendered_user_text` is only needed if `preprocessing="two_phase"` replaces the original user message with extracted requirements. If this path is used, the context should include both:

- `request`: original structured request fields.
- `preprocessed_requirements`: phase-1 extracted Markdown.

### `PromptRenderer`

Purpose: own the Jinja2 environment and strict rendering.

Recommended API:

```python
class PromptRenderer:
    def __init__(self, prompts_root: Path) -> None:
        ...

    def render(
        self,
        template_set: PromptTemplateSet,
        context: Mapping[str, Any],
    ) -> RenderedPrompt:
        ...
```

The renderer should render `examples.j2` first and inject it into `system.j2` as `examples_block`, or render both from the same context and concatenate inside `system.j2`. Default recommendation: render `examples.j2` separately and pass `examples_block` into `system.j2` to keep each artifact independently testable.

### `RenderedPrompt`

Use a dataclass:

```python
@dataclass(frozen=True)
class RenderedPrompt:
    system_prompt: str
    user_prompt: str
    prompt_version: str
    examples_version: str
    template_names: tuple[str, ...]
```

`examples_version` should initially preserve the current `EXAMPLES_VERSION` semantics if examples are still loaded from `app/context/examples.py`. If the example artifacts move into prompt versions later, `examples_version` can become `estimation/v1/examples`.

## End-to-End Flow

1. Client sends `POST /api/v1/estimate` with an `EstimationRequest`.
2. FastAPI validates and normalizes fields:
   - trims `project_summary`, `project_description`, `deliverables`, `out_of_scope`, custom names, and notes;
   - validates `target_date` for `fixed_date` and `critical`;
   - validates attachment count, size, content type, and base64.
3. Router builds an assessment surface from user-authored fields only:
   - `project_summary`
   - `project_description`
   - `deliverables`
   - `out_of_scope`
4. `EstimationService._prepare_call()`:
   - runs domain guardrails;
   - selects `EstimationMode`;
   - enforces mode eligibility;
   - applies `FORCED_ESTIMATION_MODE` when configured;
   - executes two-phase preprocessing when requested;
   - loads examples for the selected mode;
   - builds prompt context;
   - resolves prompt version;
   - renders `RenderedPrompt`.
5. `StructuredLlmClient` (Instructor + LiteLLM) receives:
   - `system_prompt=rendered.system_prompt`
   - `user_prompt=rendered.user_prompt`
   - `response_model=EstimationResult` (JSON Schema derived from the model, not hand-written).
6. Service validates provider payload into **`EstimationResult`** (Pydantic); on failure, bounded retries; on success, assembles **`EstimationResponse`** including `result`, `prompt_version`, `examples_version`, usage, assessment, and other transport metadata for stats logging and optional `evaluate` diagnostics.

## Renderer Contract

Input contract:

```python
render_estimation_prompt(
    request: EstimationRequest,
    *,
    mode: EstimationMode,
    examples: Sequence[EstimationExample],
    preprocessing: Literal["none", "inline_cleaning", "two_phase"],
    preprocessed_requirements: str | None = None,
    version: str | None = None,
) -> RenderedPrompt
```

Output contract:

- `system_prompt`: complete system message, including role, estimation rules, mode instructions, optional preprocessing instruction block, output contract, and examples.
- `user_prompt`: complete user message, including project context, scope, constraints, attachments summary/content, and requested output preferences.
- `prompt_version`: concrete version such as `estimation/v1`.
- `examples_version`: current example source/version.
- `template_names`: tuple such as `("examples.j2", "system.j2", "user.j2")`.

Failure behavior:

- Missing template file: raise `PromptTemplateNotFound`.
- Missing context key due to `StrictUndefined`: raise `PromptRenderError`.
- Invalid prompt version: raise `PromptVersionError`.
- Service boundary converts these to `EstimationError("Prompt rendering failed.")` and logs safe metadata.

## Domain and transport models (examples)

### `EstimationResult` (domain — illustrative)

Use nested models with **numeric types** the frontend can chart or tabulate. Field names are indicative; tighten during implementation.

```python
from __future__ import annotations

from pydantic import BaseModel, Field, field_validator, model_validator


class MoneyAndHours(BaseModel):
    hours: float = Field(..., ge=0)
    cost_eur: float = Field(..., ge=0)


class EstimationLineItem(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    category: str | None = Field(default=None, max_length=80)
    hours: float = Field(..., ge=0)
    cost_eur: float = Field(..., ge=0)


class EstimationPhase(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    items: list[EstimationLineItem] = Field(default_factory=list)


class EstimationTotals(MoneyAndHours):
    """Roll-up totals; validators may cross-check sum(items)."""


class EstimationResult(BaseModel):
    """Single source of truth for structured estimation output (API + LLM contract)."""

    title: str = Field(..., min_length=3, max_length=200)
    summary: str = Field(..., min_length=20, max_length=2000)
    phases: list[EstimationPhase] = Field(default_factory=list)
    line_items: list[EstimationLineItem] = Field(default_factory=list)
    totals: EstimationTotals
    duration_weeks: float = Field(..., gt=0)
    confidence: float = Field(..., ge=0.0, le=1.0)
    assumptions: list[str] = Field(default_factory=list, max_length=20)
    risks: list[str] = Field(default_factory=list, max_length=20)
    recommended_team: list[str] = Field(default_factory=list, max_length=15)
    presentation: dict[str, str] | None = Field(
        default=None,
        description="Optional UI hints derived from request.output_format; not a second schema.",
    )

    @model_validator(mode="after")
    def coherent_totals(self) -> EstimationResult:
        flat = [li for ph in self.phases for li in ph.items] + self.line_items
        if flat:
            sum_hours = sum(x.hours for x in flat)
            sum_cost = sum(x.cost_eur for x in flat)
            if abs(sum_hours - self.totals.hours) > 0.51:
                raise ValueError("totals.hours must match sum of line items (within tolerance)")
            if abs(sum_cost - self.totals.cost_eur) > 1.0:
                raise ValueError("totals.cost_eur must match sum of line items (within tolerance)")
        return self

    @field_validator("assumptions", "risks")
    @classmethod
    def non_empty_strings(cls, v: list[str]) -> list[str]:
        for s in v:
            if not s.strip():
                raise ValueError("list items must be non-empty")
        return v
```

### `EstimationResponse` (transport — illustrative)

```python
from datetime import datetime

from pydantic import BaseModel, Field

from app.services.estimation_engine import EstimationMode


class EstimationResponse(BaseModel):
    """HTTP envelope: typed result plus metadata. Replaces string-centric EstimateResponse."""

    result: EstimationResult
    prompt_version: str
    examples_version: str
    mode: EstimationMode | None = None
    model: str | None = None
    provider: str | None = None
    request_id: str | None = None
    timestamp: datetime | None = None
    latency_ms: int | None = None
    degraded: bool | None = None
    # Optional nested views for evaluate=, dev_mode, usage — align with existing patterns
```

### JSON Schema from Pydantic (normative)

- Generate at runtime: `schema = EstimationResult.model_json_schema()` (or `model_json_schema(mode="validation")` when Pydantic v2 options matter).
- Pass the schema into the structured completion path (Instructor / provider), **not** a checked-in duplicate JSON file.
- On response: `EstimationResult.model_validate(provider_object)` or Instructor’s validated instance.
- When the domain model evolves in a breaking way, bump a **`schema_version`** field inside `EstimationResult` or bump the API route version; document migration for the frontend.

### Instructor + LiteLLM pseudocode (typed return)

```python
import instructor
from litellm import completion
from app.schemas.estimation_result import EstimationResult


def build_instructor_client() -> instructor.Instructor:
    return instructor.from_litellm(completion)


def complete_estimation_structured(
    *,
    litellm_model: str,
    system_prompt: str,
    user_prompt: str,
    max_tokens: int,
) -> EstimationResult:
    client = build_instructor_client()
    return client.chat.completions.create(
        model=litellm_model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        max_tokens=max_tokens,
        response_model=EstimationResult,
    )
```

Wrap with retry loop on `ValidationError` / instructor failures; cap attempts via `STRUCTURED_OUTPUT_MAX_ATTEMPTS`.

### Versioning: prompts vs schema

- **Prompt artifacts** (`app/prompts/estimation/v1/`): versioned natural-language instructions and few-shot layout.
- **Schema contract**: versioned implicitly via **`EstimationResult`** in code (and optionally explicit `schema_version` in the model). Rollback of bad prompts does not require a schema change if the contract is unchanged; breaking domain changes require coordinated **API + frontend** updates.

## Mapping `EstimationRequest` to Jinja2 Context

Build a flat, readable context with explicit sub-objects rather than passing the raw Pydantic model directly.

Recommended structure:

```python
{
    "prompt": {
        "use_case": "estimation",
        "version": "estimation/v1",
        "mode": "professional",
        "preprocessing": "inline_cleaning",
        "structured_outputs_ready": True,
    },
    "project": {
        "name": request.project_name,
        "summary": request.project_summary,
        "type": request.project_type.value,
        "industry": "other: Legal tech" or "fintech",
        "target_audience": "other: Regional franchise owners" or "b2b_smb",
        "description": request.project_description,
    },
    "scope": {
        "deliverables": request.deliverables,
        "out_of_scope": request.out_of_scope or [],
    },
    "delivery": {
        "urgency": request.delivery_urgency.value,
        "target_date": request.target_date.isoformat() if request.target_date else None,
        "approach": request.delivery_approach.value if request.delivery_approach else None,
        "has_fixed_deadline": bool(request.target_date),
    },
    "technical": {
        "integration_categories": [item.value for item in request.integration_categories],
        "integration_custom_names": request.integration_custom_names or [],
        "has_integrations": bool(request.integration_categories or request.integration_custom_names),
        "data_sensitivity": request.data_sensitivity.value,
        "hosting_constraints": [item.value for item in request.hosting_constraints or []],
        "hosting_notes": request.hosting_notes,
        "ui_languages": [item.value for item in request.ui_languages],
    },
    "risk": {
        "level": request.risk_level.value if request.risk_level else "unknown",
        "external_dependencies": request.external_dependencies or [],
    },
    "output": {
        "detail_level": request.detail_level.value,
        "format": request.output_format.value,
        "sections": [...],
        "requires_table": request.output_format.value == "phases_table",
        "requires_line_items": request.output_format.value == "line_items",
        "requires_narrative": request.output_format.value == "narrative",
    },
    "attachments": {
        "items": [...],
        "has_items": bool(request.attachments),
        "count": len(request.attachments),
    },
    "examples": [...],
    "preprocessed_requirements": "...",
}
```

Do not expose base64 blobs to templates. Decode text/Markdown attachments in Python and expose bounded text. For PDFs, expose metadata only unless a future OCR/extraction pipeline exists.

Recommended attachment item:

```python
{
    "filename": "requirements.md",
    "content_type": "text/markdown",
    "text": "...decoded text...",
    "is_text": True,
    "is_pdf": False,
}
```

## Dynamic Rendering Rules

### `detail_level`

Map to explicit output depth instructions:

- `summary`: concise estimate, fewer assumptions, high-level phases, avoid deep task breakdown.
- `medium`: balanced estimate, include phases/tasks, assumptions, risks, and recommended team.
- `detailed`: full breakdown, dependencies, risk buffers, validation questions, assumptions by area, and scenario bands.

Keep this mapping in Python:

```python
DETAIL_LEVEL_GUIDANCE = {
    "summary": "Produce a concise executive estimate...",
    "medium": "Produce a balanced delivery estimate...",
    "detailed": "Produce a detailed planning estimate...",
}
```

Templates should render `{{ output.detail_guidance }}` instead of branching across many sections.

### `output_format`

**Rule:** `output_format` (`phases_table` | `line_items` | `narrative`) influences **prompt instructions and optional `presentation` hints** inside the same stable **`EstimationResult`** contract. It **must not** switch the HTTP response to a different top-level JSON shape or alternate ad-hoc schemas per format.

**Prompt mapping (Python → Jinja context):**

- `phases_table`: emphasize populating `phases` with ordered work breakdown; line items may still exist but phases are primary for UI.
- `line_items`: emphasize granular `line_items` and roll-ups; phases may be coarse or a single phase.
- `narrative`: encourage rich `assumptions`, `risks`, and `notes` text fields while still requiring numeric totals and structured lists the UI can render.

**Stable domain shape:** `EstimationResult` always includes the fields needed for any view (e.g. `title`, `phases`, `line_items`, `totals`, `duration_weeks`, `confidence`, `assumptions`, `risks`, `recommended_team`). Empty lists are allowed where validators permit. **Validators** enforce cross-field coherence, not Markdown headings.

Default recommendation: keep **totals and duration** mandatory in `EstimationResult`; keep **presentation hints** optional and small so the frontend can choose layout without parsing prose.

### `attachments`

Rules:

- If no attachments: render "No supporting documents were provided."
- Text/Markdown attachments: include decoded content under "Supporting documents" with filename and content type.
- PDF attachments: include filename and content type only, with a warning that binary content was not parsed.
- Never pass base64 to templates.
- Cap decoded text in Python if needed before rendering.

### `integration_categories`

Rules:

- No categories and no custom names: instruct model to assume no explicit third-party integration beyond normal hosting/dev tooling.
- Known categories: render normalized values and ask model to account for implementation, credentials/configuration, testing, and operational risk.
- `other` with `integration_custom_names`: render custom names as concrete integrations to estimate.
- `third_party_api_unknown`: instruct model to add discovery/integration uncertainty.

### `hosting_constraints`

Rules:

- `no_preference`: estimate for standard managed cloud deployment unless other fields imply otherwise.
- `cloud_managed`: include cloud managed services and standard DevOps.
- `customer_cloud_only`: include tenant/account constraints and environment handoff.
- `on_prem`: include deployment packaging, infrastructure coordination, and support overhead.
- `air_gapped`: include major delivery risk, offline dependency handling, and stricter validation.
- `hybrid`: include networking, identity, and data synchronization risk.

Map these to Python guidance strings so templates stay readable.

### `ui_languages`

Rules:

- Empty list: no explicit localization requirement.
- One language: mention UI/content language.
- More than one language: instruct model to include localization/i18n effort, content review, QA across languages, and possible copy/legal review.
- `other`: render as explicit unknown/other language and recommend clarification.

### `delivery_urgency` / `target_date`

Rules:

- `flexible`: allow realistic sequencing and buffers.
- `standard`: use normal delivery assumptions.
- `fixed_date`: require deadline feasibility notes using `target_date`.
- `critical`: require explicit risk warning, scope trade-offs, and recommended MVP cut line using `target_date`.

The template should render prepared booleans:

- `delivery.has_fixed_deadline`
- `delivery.requires_tradeoff_warning`
- `delivery.target_date`

### `preprocessing`

Rules:

- `none`: render the original structured request.
- `inline_cleaning`: render an instruction block in the system prompt telling the model to normalize informal or contradictory input before estimating.
- `two_phase`: run existing extraction first, then render both original request summary and `preprocessed_requirements`; user prompt should tell the model to estimate from extracted requirements while using original request fields for constraints and metadata.

Default recommendation: keep two-phase extraction outside Jinja2. Jinja2 only renders the result.

## Template Examples

### `system.j2`

```jinja2
You are a senior software estimation assistant for professional delivery planning.

Use case: {{ prompt.use_case }}
Prompt version: {{ prompt.version }}
Estimation mode: {{ prompt.mode }}

Your job is to produce a realistic software project estimate from a guided-form request.
You must respond with **structured JSON only** matching the server **EstimationResult** schema (enforced by the API). Do not use Markdown tables or free-form prose as the primary output.

Prioritize concrete delivery work, assumptions, risks, dependencies, and verification needs.

{% if prompt.preprocessing == "inline_cleaning" %}
Before estimating, normalize noisy input:
- Ignore off-topic filler.
- Surface implicit requirements.
- Resolve contradictions by favoring the most recent or most specific requirement.
- Keep only software delivery requirements relevant to the estimate.
{% endif %}

## Output depth
{{ output.detail_guidance }}

## Output format
{{ output.format_guidance }}

{% include "partials/output_contract.md.j2" %}

{% if prompt.structured_outputs_ready %}
{% include "partials/structured_output_hint.md.j2" %}
{% endif %}

{{ examples_block }}
```

### `examples.j2`

```jinja2
## Reference estimation examples

{% if examples %}
{% for example in examples %}
### Example {{ loop.index }} — meeting summary
{{ example.meeting_summary }}

### Example {{ loop.index }} — estimate
{{ example.estimation }}
{% endfor %}
{% else %}
No reference examples are available for this mode. Do not invent examples.
{% endif %}
```

**Few-shot migration:** `example.estimation` should evolve from Markdown-only samples to **JSON text that validates as `EstimationResult`** (or structured excerpts), so few-shot demonstrations match the enforced response contract.

### `user.j2`

```jinja2
## Product context

{% if project.name %}
- Name / code: {{ project.name }}
{% endif %}
- Summary: {{ project.summary }}
- Project type: {{ project.type }}
- Target audience: {{ project.target_audience }}
{% if project.industry %}
- Industry: {{ project.industry }}
{% endif %}

## Project description

{{ project.description }}

## Scope

### Deliverables
{% for item in scope.deliverables %}
- {{ item }}
{% endfor %}

{% if scope.out_of_scope %}
### Out of scope
{% for item in scope.out_of_scope %}
- {{ item }}
{% endfor %}
{% endif %}

## Delivery constraints

- Urgency: {{ delivery.urgency }}
{% if delivery.target_date %}
- Target date: {{ delivery.target_date }}
{% endif %}
{% if delivery.approach %}
- Delivery approach: {{ delivery.approach }}
{% endif %}
{% if delivery.requires_tradeoff_warning %}
- Deadline note: explicitly discuss feasibility, scope trade-offs, and risk of the requested date.
{% endif %}

## Integrations, data, and hosting

{% if technical.has_integrations %}
- Integrations: {{ technical.integration_categories | join(", ") }}
{% if technical.integration_custom_names %}
- Custom integration names: {{ technical.integration_custom_names | join("; ") }}
{% endif %}
{% else %}
- Integrations: none explicitly indicated.
{% endif %}
- Data sensitivity: {{ technical.data_sensitivity }}
{% if technical.hosting_constraints %}
- Hosting constraints: {{ technical.hosting_constraints | join(", ") }}
{% endif %}
{% if technical.hosting_notes %}
- Hosting notes: {{ technical.hosting_notes }}
{% endif %}
{% if technical.ui_languages %}
- UI/content languages: {{ technical.ui_languages | join(", ") }}
{% endif %}

## Risks and dependencies

- Perceived risk level: {{ risk.level }}
{% if risk.external_dependencies %}
External dependencies:
{% for item in risk.external_dependencies %}
- {{ item }}
{% endfor %}
{% endif %}

## Output preferences

- Detail level: {{ output.detail_level }}
- Output format: {{ output.format }}

{% if preprocessed_requirements %}
## Preprocessed requirements

Estimate primarily from these extracted requirements. Use the original request fields above as constraints and metadata.

{{ preprocessed_requirements }}
{% endif %}

{% include "partials/request_context.md.j2" %}
```

### `partials/output_contract.md.j2`

```jinja2
## Required machine-readable output

Return **only** a JSON object that conforms to the server-side **EstimationResult** schema (structured output / tool mode). Do not wrap JSON in Markdown fences. Do not add commentary outside JSON.

The object must include at minimum:
- `title`, `summary`, `totals` (hours and cost_eur), `duration_weeks`, `confidence`
- `phases` and/or `line_items` populated according to output format guidance below
- `assumptions`, `risks`, `recommended_team` as string lists

{% if output.requires_table %}
Emphasize `phases`: each phase has a `name` and `items` with hours and cost_eur.
{% elif output.requires_line_items %}
Emphasize `line_items`: granular rows with hours and cost_eur; phases may be minimal.
{% elif output.requires_narrative %}
Still fill structured lists and numeric totals; use `summary` and list items for narrative depth.
{% endif %}
```

### `partials/request_context.md.j2`

```jinja2
{% if attachments.has_items %}
## Supporting documents

{% for attachment in attachments.items %}
### {{ attachment.filename }} ({{ attachment.content_type }})
{% if attachment.is_pdf %}
Binary PDF content was provided but not parsed. Use only the filename and metadata as weak context.
{% elif attachment.text %}
{{ attachment.text }}
{% else %}
No readable text content after decoding.
{% endif %}
{% endfor %}
{% else %}
## Supporting documents

No supporting documents were provided.
{% endif %}
```

### `partials/structured_output_hint.md.j2`

```jinja2
## Structured JSON output (required)

The API validates your reply with **Pydantic**. If any required field is missing or numeric totals disagree with line items, the request fails.

Match field names and types exactly. Use numbers (not strings) for hours, costs, weeks, and confidence.
```

## Renderer Pseudocode

```python
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from jinja2 import Environment, FileSystemLoader, StrictUndefined, TemplateError


@dataclass(frozen=True)
class RenderedPrompt:
    system_prompt: str
    user_prompt: str
    prompt_version: str
    examples_version: str
    template_names: tuple[str, ...]


class PromptRenderError(RuntimeError):
    """Raised when a prompt template cannot be rendered safely."""


class PromptRenderer:
    def __init__(self, prompts_root: Path) -> None:
        self._env = Environment(
            loader=FileSystemLoader(prompts_root),
            undefined=StrictUndefined,
            trim_blocks=True,
            lstrip_blocks=True,
            autoescape=False,
        )

    def render(self, template_set: PromptTemplateSet, context: Mapping[str, Any]) -> RenderedPrompt:
        try:
            examples_template = self._env.get_template(
                f"{template_set.use_case}/{template_set.version}/{template_set.examples_template}"
            )
            examples_block = examples_template.render(**context).strip()

            system_template = self._env.get_template(
                f"{template_set.use_case}/{template_set.version}/{template_set.system_template}"
            )
            system_prompt = system_template.render(**context, examples_block=examples_block).strip()

            user_template = self._env.get_template(
                f"{template_set.use_case}/{template_set.version}/{template_set.user_template}"
            )
            user_prompt = user_template.render(**context).strip()
        except TemplateError as exc:
            raise PromptRenderError("failed to render prompt template") from exc

        return RenderedPrompt(
            system_prompt=system_prompt + "\n",
            user_prompt=user_prompt + "\n",
            prompt_version=f"{template_set.use_case}/{template_set.version}",
            examples_version=context["examples_version"],
            template_names=(
                template_set.examples_template,
                template_set.system_template,
                template_set.user_template,
            ),
        )
```

Implementation note: use one `Environment` rooted at `app/prompts/` so Jinja includes such as `{% include "estimation/v1/partials/output_contract.md.j2" %}` work consistently. If relative includes are preferred, configure templates and paths carefully and cover them with tests.

## Versioning and Rollback Strategy

### Versioning

- Prompt versions are immutable directories after release (`app/prompts/estimation/v1/`, `v2/`, …).
- **Schema contract** versions track the **`EstimationResult`** Pydantic model in code (optional explicit `schema_version` field on the model for client debugging).
- `v1` is the first Jinja2 + **structured JSON output** implementation for the guided-form estimator.
- `v2` is created when either prompts **or** the domain output model change in a breaking way; coordinate with frontend and OpenAPI.

### Rollback

- **Prompts:** select a previous directory (`PROMPT_ESTIMATION_VERSION=v1`) when only natural-language instructions regress.
- **Schema:** rollback or forward-fix the **`EstimationResult`** Pydantic model (and coordinated frontend types). Prompt rollback alone cannot fix a broken domain schema.
- No code changes required for prompt-only rollback if `PromptTemplateSet` paths stay compatible.

### Metadata

Use metadata values that are useful in logs and response dev metadata:

- `prompt_version = "estimation/v1"`
- `examples_version = "file-mode-v4-estimator-layout"` initially
- future `examples_version = "estimation/v2/examples"` if examples move into versioned prompt assets

## Testing Strategy

### Unit tests: context builder

Add `tests/test_prompt_context.py`:

- Maps `ProjectType`, `TargetAudience.other`, and `Industry.other` into readable strings.
- Converts dates to ISO strings.
- Converts enum lists to value lists.
- Sets `technical.has_integrations` correctly for no integrations, known integrations, custom names, and `third_party_api_unknown`.
- Sets delivery flags for `fixed_date` and `critical`.
- Decodes text/Markdown attachments.
- Represents PDF attachments as metadata only.
- Does not expose base64 content in context.
- Produces deterministic context for snapshot-friendly rendering.

### Unit tests: renderer

Add `tests/test_prompt_renderer.py`:

- Renders `system_prompt` and `user_prompt` for a valid sample request.
- Fails on missing template variables because of `StrictUndefined`.
- Fails clearly for unknown prompt version.
- Includes `examples_block` in the system prompt.
- Normalizes final newlines.
- Does not autoescape Markdown content.

### Conditional rendering tests

Add `tests/test_estimation_prompt_rendering.py`:

- `detail_level=summary` renders concise-output guidance.
- `detail_level=detailed` renders detailed-planning guidance.
- `output_format=phases_table` renders JSON-emphasis guidance for `phases` in prompts.
- `output_format=line_items` renders JSON-emphasis guidance for `line_items` in prompts.
- `output_format=narrative` still requires structured numeric totals and populated lists in **`EstimationResult`** (not Markdown).
- `delivery_urgency=critical` with `target_date` renders trade-off warning.
- Multiple `ui_languages` render i18n/QA guidance.
- `hosting_constraints=["air_gapped"]` renders high-risk deployment guidance.
- `preprocessing=inline_cleaning` renders the cleaning block.
- `preprocessing=two_phase` renders extracted requirements in the user prompt.

### Unit tests: `EstimationResult` schema and validators

Add `tests/test_estimation_result_schema.py` (name illustrative):

- `model_json_schema()` contains expected keys and required fields for the public contract.
- Valid fixture JSON round-trips through `EstimationResult.model_validate`.
- Invalid fixtures fail with clear `ValidationError` cases (wrong types, totals mismatch, empty strings).
- `output_format` does not change the set of top-level keys on `EstimationResult`.

### Unit tests: structured client (mocked)

Add `tests/test_structured_llm_client.py`:

- Mock LiteLLM / Instructor so tests do not call real providers.
- Successful path returns `EstimationResult` instance.
- Validation failure triggers retry up to `N` then surfaces configured HTTP error.

### Regression tests

Add stable fixture-based tests:

```text
tests/fixtures/estimation_requests/
├── medium_phases_table.json
├── detailed_line_items_with_attachments.json
└── critical_multilingual_air_gapped.json
```

Recommended assertion strategy:

- Keep full snapshots only if the team accepts snapshot churn.
- Otherwise assert stable semantic fragments:
  - required section names,
  - selected dynamic guidance,
  - no raw base64,
  - selected prompt version,
  - examples block marker.

### Integration tests

Update existing service/router tests:

- `POST /api/v1/estimate` returns **`EstimationResponse`** with **`result: EstimationResult`** (typed), not a Markdown `estimation` string as the primary payload.
- Mocked provider returns JSON matching `EstimationResult`; response passes OpenAPI / FastAPI `response_model` checks.
- Stats / dev metadata still include `prompt_version` and `examples_version`.
- **`/estimate/stream`:** per Open questions, assert the chosen behavior (e.g. single terminal SSE event carrying validated JSON, or interim v2 route without streaming).

### Manual checks

Run:

```bash
uv run pytest tests/test_prompt_context.py tests/test_prompt_renderer.py tests/test_estimation_prompt_rendering.py
uv run pytest
uv run uvicorn app.main:app --reload
```

Then submit a known request from `api-collection/Estimador CAG/` or `curl` and confirm the JSON body parses as **`EstimationResponse`** with a non-empty **`result`**. In the **`web/`** app, confirm at least one view (table or cards) binds **directly** to `result.phases`, `result.line_items`, or `result.totals` **without** parsing Markdown.

## Risks and Design Decisions

### Risk: too much business logic in templates

Decision: templates may contain simple presentation conditionals and loops only. Enum interpretation, fallback values, attachment decoding, deadline flags, output guidance, and hosting guidance belong in Python context builders.

### Risk: prompt regressions are hard to review

Decision: keep prompt files small and versioned. Add fragment-based regression tests for high-risk dynamic branches instead of relying only on visual review.

### Risk: random examples make prompt regression tests flaky

Decision: renderer tests pass explicit examples. Service tests can seed randomness or mock `load_examples(mode)`.

### Risk: StrictUndefined causes runtime failures

Decision: this is intentional. Missing context should fail fast. Cover all released templates with render tests and convert runtime failures into safe `EstimationError` messages.

### Risk: structured outputs vs streaming UX

Decision: resolve explicitly in Open questions; default to **non-tokenized** structured completion for the primary path until a supported incremental structured protocol exists.

### Risk: Markdown / regex evaluation vs Pydantic

Decision: **remove reliance** on `evaluate_estimation_structure` and Markdown regex gates for the primary success path. Replace with **`EstimationResult` validators** and optional secondary quality models. Any legacy Markdown scoring remains dev-only or is deleted.

### Risk: Instructor + LiteLLM version drift

Decision: pin versions in `pyproject.toml` / `uv.lock`; add smoke tests against mocked structured responses; document supported provider matrix in `docs/technical/README.md`.

### Risk: duplicated prompt versions drift

Decision: only create a new version for meaningful behavior changes. Use shared partials within a version, but avoid cross-version imports so rollback is self-contained.

## Implementation Plan

### Phase 1: Dependencies and prompt rendering foundation

1. Add `uv add jinja2 instructor` (LiteLLM already present).
2. Create `app/prompts/estimation/v1/` with `manifest.toml`, `system.j2`, `user.j2`, `examples.j2`, and partials aligned with **JSON `EstimationResult`** output (few-shot examples should evolve toward **valid JSON-shaped** illustrations, not Markdown-only estimates).
3. Add `app/services/prompt_versions.py`, `prompt_context.py`, `prompt_renderer.py`.
4. Add focused unit tests for version resolution and template rendering.

### Phase 2: Domain and transport models (Pydantic-first)

1. Add `app/schemas/estimation_result.py` with **`EstimationResult`** nested models, validators, and documented `model_json_schema()` usage.
2. Add `app/schemas/estimation_response.py` with **`EstimationResponse`** (`result` + metadata).
3. Rename the existing **`EstimationResult`** dataclass in `app/services/llm_service.py` to avoid collision (e.g. `LlmEstimationCallOutcome`).
4. Unit tests: schema generation, valid/invalid payloads, business validators.

### Phase 3: Structured LLM port (Instructor + LiteLLM)

1. Implement `app/services/structured_llm_client.py` with `complete_structured(..., response_model=EstimationResult)` and bounded retries (`STRUCTURED_OUTPUT_MAX_ATTEMPTS`).
2. Wire model id / timeout from existing `Settings`; no provider-specific branches outside this module.
3. Mock-based tests for success and retry-exhausted paths.

### Phase 4: Integrate prompts + structured completion in `EstimationService`

1. Keep assessment-surface rendering deterministic and separate.
2. Replace `build_system_prompt()` / `render_estimation_user_message()` in the main path with `render_estimation_prompt()`.
3. Preserve preprocessing behavior (`none`, `inline_cleaning`, `two_phase`).
4. Call **`complete_structured`** instead of free-text `provider.complete` for the final estimate.
5. Assemble **`EstimationResponse`** with `result: EstimationResult`, `prompt_version`, `examples_version`, usage, assessment, etc.
6. Update stats logging; remove or replace Markdown `structure_evaluation` with schema-aware diagnostics when `evaluate=true`.

### Phase 5: HTTP layer and frontend

1. Update `app/routers/estimations.py` and `app/schemas/estimations.py` (or new response module) so **`response_model`** reflects **`EstimationResponse`**; document breaking change or v2 route per Open questions.
2. Update **`web/`** to render estimation UI from **`response.result`** fields only (tables/cards), with **no Markdown parser** as the primary path.
3. Resolve **`/estimate/stream`** behavior and tests.

### Phase 6: Documentation and lockfile

1. Update `docs/technical/README.md`: dual contracts, Instructor+LiteLLM, schema versioning, streaming decision.
2. Update `README.md` / `.env.example` for new env vars (`STRUCTURED_OUTPUT_MAX_ATTEMPTS`, optional `PROMPT_ESTIMATION_VERSION`).
3. Run `uv run pytest` and sync mirrored docs if applicable.

## Acceptance Criteria

- [ ] `jinja2` and `instructor` are runtime dependencies in `pyproject.toml` and locked in `uv.lock` (LiteLLM already declared).
- [ ] **Inbound contract** remains `EstimationRequest`; **outbound domain** is `EstimationResult`; **transport** is `EstimationResponse` with `result` as the primary payload.
- [ ] JSON Schema for the LLM is **derived only** from `EstimationResult` (e.g. `model_json_schema()`); no hand-maintained duplicate schema files.
- [ ] Structured completion uses a **single** `StructuredLlmClient` (Instructor + LiteLLM); no provider-specific structured-output code in routers or prompt builders.
- [ ] Service-internal naming collision with legacy `EstimationResult` in `llm_service.py` is **resolved**.
- [ ] Versioned prompt artifacts exist under `app/prompts/estimation/v1/` and instruct JSON **`EstimationResult`** output.
- [ ] The renderer uses `FileSystemLoader`, `StrictUndefined`, `trim_blocks=True`, and `lstrip_blocks=True`.
- [ ] There is one public Python entry point for estimation prompt rendering.
- [ ] `EstimationRequest` maps to Jinja context without raw base64 in templates.
- [ ] `output_format` affects **prompt guidance** (and optional `presentation` hints) but **not** alternate top-level API shapes.
- [ ] Bounded **retries** on schema/validation failure; exhausted retries return a documented safe HTTP error.
- [ ] `evaluate=true` diagnostics are **schema-aware**; Markdown regex evaluation is not the primary quality gate.
- [ ] **`POST /api/v1/estimate`** returns a validated **`EstimationResponse`**; the frontend renders **directly** from `result` **without** free-text parsing.
- [ ] **Changing provider/model** (via LiteLLM / settings) does **not** require changing **`EstimationResult`** field definitions.
- [ ] The router remains free of prompt construction and provider SDK calls.
- [ ] Stats / dev metadata include `prompt_version` and `examples_version`.
- [ ] Documentation covers dual contracts, structured-output flow, streaming decision, and frontend binding expectations.

## Test Plan

- Unit tests:
  - `uv run pytest tests/test_prompt_context.py tests/test_prompt_renderer.py tests/test_estimation_prompt_rendering.py`
  - `uv run pytest tests/test_estimation_result_schema.py tests/test_structured_llm_client.py`
- Integration tests:
  - API returns `EstimationResponse` with mocked structured JSON from the provider adapter.
  - Streaming behavior per chosen Open-questions outcome.
- Manual checks:
  - `uv run uvicorn app.main:app --reload`
  - `curl` or API collection: response body is typed JSON with `result.totals`, `result.phases` / `result.line_items`, etc.
  - **`web/`**: at least one screen renders a table or estimation view from **`result`** fields only.

## Documentation Plan

- Update `docs/technical/README.md`:
  - dual contracts (`EstimationRequest` vs `EstimationResult` / `EstimationResponse`),
  - Pydantic → JSON Schema → LLM → validate pipeline,
  - Instructor + LiteLLM abstraction,
  - prompt vs schema versioning and rollback,
  - removal of Markdown-first client contract,
  - streaming structured-output decision.
- Update `README.md` and **`.env.example`** for `STRUCTURED_OUTPUT_MAX_ATTEMPTS`, optional `PROMPT_ESTIMATION_VERSION`, and any new settings.
- Update OpenAPI-exposed schema descriptions for the new response type.
- Keep technical prose in English.

## Repository commits (master-ia)

| Short hash | Message | Scope / summary |
|------------|---------|-----------------|
| `3497d74` | `docs(work-items): add feature-011 Jinja2 and structured output spec` | Track the full feature-011 specification in the versioned `docs/work-items/` mirror so it ships with the repository. |
| `05c841a` | `docs(work-items): fix repository commit log hash in feature-011` | Replace the incorrect short hash in the commit log row with `3497d74` for the initial mirror commit. |
