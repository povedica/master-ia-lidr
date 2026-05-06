# Feature: Streamlit internal UI for estimador-cag

## Objective

Add a lightweight **Streamlit** front end to **`proyectos/estimador-cag`** so testers and demos can run meeting transcriptions through the existing estimation pipeline **in a browser**, without crafting HTTP payloads or shell commands. FastAPI remains the primary API surface; Streamlit is for **manual validation and demos** only.

## Context

**Canonical application package:** `proyectos/estimador-cag/app/` (`uv` project `estimador-cag`, `packages = ["app"]` in that subfolder’s `pyproject.toml`).

**Existing layering:**

| Area | Role |
|------|------|
| `app/routers/estimations.py` | HTTP API; constructs `EstimationService` via `get_settings()`, `build_provider_chain(settings)` |
| `app/services/llm_service.py` | `EstimationService` orchestration (modes, prompts, provider chain); **async** `estimate(...)` entry point |
| `app/services/providers/` | Provider chain; no direct SDK use from routes |
| `app/config.py` | `Settings` + `get_settings()` (`pydantic-settings`, `.env` beside app root) |

**Naming note:** Business logic lives in `llm_service.py` under an `EstimationService` class—not a standalone `generate_response(...)` helper. The UI must call that service layer (same construction pattern as `get_estimation_service` in `estimations.py`).

**Out of repo root (`master-ia` package `app/`):** FastAPI exposes `POST /llm/demo` with logic in `llm_demo.py` and **no** `services/` split. That path is **out of scope** for this document unless a separate work item explicitly targets it.

## Scope

### Includes

- New entry point: `proyectos/estimador-cag/app/streamlit_app.py`.
- Add **Streamlit** as a dependency of the **estimador-cag** `pyproject.toml` (via `uv add streamlit` from `proyectos/estimador-cag/`); keep existing dependencies.
- UI: title, short description, text area for transcript, optional controls (minimum: **preprocessing** mode aligned with service: `none` | `inline_cleaning` | `two_phase`), submit, response area, `st.error` for failures.
- Call chain: **Streamlit → `EstimationService` (`estimate`) → providers**—no OpenAI/Anthropic clients inside the Streamlit file.
- Configuration via **`from app.config import get_settings`** (or inject `Settings` into a thin factory mirroring FastAPI deps). No hardcoded keys, model IDs, or base URLs.
- User-facing validation: empty transcript → clear message without calling the service.
- Safe errors: distinguish “no API key / misconfiguration”, domain guardrail rejection, estimation failure, timeouts—**without** leaking stack traces, secrets, or raw provider payloads.
- Async: `estimate` is `async`; use a single-threaded approach appropriate for Streamlit (`asyncio.run(...)`) or another documented supported pattern—**no** duplicate business logic inside the UI file beyond orchestration.

### Excludes

- Auth, multi-user tenancy, persistence, production deployment hardening.
- Replacing FastAPI or duplicating routers inside Streamlit.
- Long conversational memory; evaluation harness; cost/token dashboards (listed only as future extensions).

## Functional Requirements

### Entry point and run command

- File: `app/streamlit_app.py` inside **estimador-cag**.
- Runnable from **`proyectos/estimador-cag`** (so imports resolve):

```bash
cd proyectos/estimador-cag
uv sync
uv run streamlit run app/streamlit_app.py
```

(Document the same in the estimador-cag README or docs mirror.)

### Minimum UI widgets

Use at least: `st.set_page_config`, `st.title`, `st.text_area`, `st.button`, `st.write`, `st.error`, plus `st.spinner` during `estimate`.

### Service reuse

- Build `EstimationService` the same way as **`get_estimation_service`** in ```66:69:proyectos/estimador-cag/app/routers/estimations.py``` (same `get_settings()`, `build_provider_chain(settings)` import source).
- If both FastAPI and Streamlit would duplicate dependency wiring, optionally extract a small `app/deps.py` factory—only if kept minimal and covered by tests or explicit manual verification.

### Errors to handle explicitly

| Case | Behaviour |
|------|-----------|
| Empty / whitespace transcript | `st.error` with a plain language message; no provider call |
| Missing or invalid credentials / `ProviderConfigError` surfaced as safe message | Friendly message referencing configuration (environment / `.env`), not raw exception text if it could contain sensitive data |
| `DomainGuardrailError` | Explain domain limitation in user-safe terms (aligned with API behaviour) |
| `EstimationError` and exhausted provider chain | Short, actionable message |
| Unexpected exceptions | Generic failure message; log server-side if logging is available from the app context without echoing details to the UI |

## Technical Approach

1. **Dependencies:** `uv add streamlit` in `proyectos/estimador-cag/`.
2. **`streamlit_app.py`:** layout + read inputs; on submit, validate non-empty text; construct `EstimationService`; `asyncio.run(service.estimate(transcription, preprocessing=...))`; render `EstimationResult.estimation` and optional metadata (provider, model, mode) in `st.write` / `st.code` as appropriate.
3. **Settings:** load via `get_settings()`; never read `OPENAI_API_KEY` directly in the Streamlit file.
4. **Optional:** small pure helper functions (e.g. format error message) in a separate module under `app/` if the Streamlit file would otherwise grow—keep `streamlit_app.py` mostly UI + one service call.

## Acceptance Criteria

- [x] Streamlit is listed in **estimador-cag** `pyproject.toml` / `uv.lock` after `uv add`.
- [x] `uv run streamlit run app/streamlit_app.py` starts from `proyectos/estimador-cag` without import errors.
- [x] UI shows title, description, input, submit, output, and error areas.
- [x] Submitting non-empty valid estimation-domain text returns an estimate **through `EstimationService.estimate`**.
- [x] Empty input is blocked in the UI with a clear error.
- [x] Configuration / provider failures show **safe** messages (no secrets, no full tracebacks in the browser).
- [x] No new business logic duplicates the estimation pipeline; no direct provider SDK usage in `streamlit_app.py`.

## Test Plan

- **Unit tests:** If any pure helper is extracted (e.g. message mapping from exception types), test it with `pytest` and mocks—**no** real API keys.
- **Integration:** Optional async test that instantiates `EstimationService` with mocked providers (existing project patterns); Streamlit itself is **not** required to be under automated UI tests.
- **Manual checks:**
  - Empty submit → error.
  - Valid transcript with keys unset → clear configuration error.
  - Valid transcript with keys set (or static fallback only, per env) → estimate renders.
  - Out-of-domain input → guardrail message matches safe expectations.

## Documentation Plan

- Update **`proyectos/estimador-cag/README.md`** (or linked doc) with: purpose of Streamlit UI, `uv run streamlit run ...`, required env vars (reference existing `.env.example` if present).
- After any Second Brain sync, mirror updates via `bash scripts/sync-estimador-cag-docs.sh` from repo root if applicable.

## Baby Steps (implementation order)

1. Add Streamlit dependency with `uv` and confirm `uv sync` clean.
2. Add `app/streamlit_app.py` minimal shell (static text + empty validation only); run locally.
3. Wire `get_settings` + `build_provider_chain` + `EstimationService` and `asyncio.run(estimate(...))`; display result.
4. Map exception types to safe `st.error` messages; add preprocessing control.
5. Manual pass per test plan; add unit tests only for extracted pure helpers if any.

## Verification

| Item | Status |
|------|--------|
| `uv run pytest` (estimador-cag) after changes | Verified (101 tests, incl. `test_streamlit_error_messages`) |
| Streamlit manual smoke (commands above) | Not verified in this session (no long-lived browser run); module import verified |
| No secrets in repo | Verified (no `.env`, no keys added) |

## Future Extensions (non-binding)

Prompt templates, file upload, transcript history in `st.session_state`, model override UI (respecting settings), token/cost surfacing from `EstimationResult.usage`, response evaluation widgets.

---

## Repository commits (master-ia)

| Short hash | Message | Scope / summary |
|------------|---------|-----------------|
| `cef8a0d` | `chore(estimador-cag): add streamlit dependency` | Adds `streamlit` to subproject `pyproject.toml` and `uv.lock`. |
| `c5dfc26` | `feat(estimador-cag): add streamlit estimation demo ui` | `streamlit_app.py`, `streamlit_error_messages.py`, pytest coverage, README run instructions. |
| `3a1184c` | `docs(cursor): align start-task with baby-steps tdd workflow` | Rewrites `.cursor/commands/start-task.md` with phased TDD / baby-steps flow for `master-ia`. |
| `a5781c3` | `docs(estimador-cag): add feature-005 streamlit work item and commit log` | Adds this work-item file and the commit table above. |

