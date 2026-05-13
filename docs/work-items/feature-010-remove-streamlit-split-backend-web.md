# Feature: Remove Streamlit and split the demo into Backend API + Web presentation layer

## Objective

Replace the current Streamlit demo with an independent web frontend that consumes the existing FastAPI backend over HTTP. The backend remains the single owner of estimation logic, prompt construction, provider orchestration, and response shaping; the new web layer owns only user interaction and presentation.

## Context

- The repository already has a working FastAPI backend under `app/`, with entrypoint `app/main.py`, router `app/routers/estimations.py`, structured request schema `app/schemas/estimation_request.py`, and service orchestration in `app/services/llm_service.py`.
- The current Streamlit UI lives in `app/streamlit_app.py`, but it already behaves as a client: it sends structured JSON to `POST /api/v1/estimate/stream` over HTTP/SSE and renders the streamed response. This migration should preserve that separation and remove the Streamlit-specific runtime and dependency.
- `pyproject.toml` still includes `streamlit`, and `docker-compose.yml` still starts a `streamlit` service on port `8501`.
- The backend does not currently configure CORS, so a browser frontend hosted on a different origin would fail without explicit origin handling.
- The current public API contract is already centered on the guided-form `EstimationRequest`; this feature should not broaden scope by redesigning the estimation contract unless implementation discovers a blocking issue.
- **Theme preference (this update):** The web app must offer an explicit appearance control: **dark**, **light**, or **system** (follow OS/browser `prefers-color-scheme`). Default is **system**. Persist the user’s choice across sessions (for example `localStorage`) so it does not reset on reload.

## Scope

### Includes

- Remove Streamlit from the active runtime, dependencies, Compose wiring, and developer documentation.
- Add a new independent frontend under `web/` that talks to the FastAPI backend via HTTP only.
- Keep the backend package under `app/`; do not move estimator logic into the frontend.
- Add backend CORS configuration for local frontend development.
- Update local run instructions so backend and frontend can be started independently.
- Theme appearance control in the web UI: **dark**, **light**, or **system**, default **system**, persisted client-side.

### Excludes

- No authentication, user accounts, persistence, estimation history, or file storage changes.
- No estimator business-logic redesign beyond the extraction/refactoring strictly required by the migration.
- No forced API route rename; keep existing endpoints such as `POST /api/v1/estimate` and `POST /api/v1/estimate/stream` unless a follow-up work item explicitly changes them.
- No SSE redesign, background jobs, Langfuse rollout, or cloud deployment work in this feature.

## Functional Requirements

### FR-01: Remove Streamlit dependency and runtime

- Remove `streamlit` from `pyproject.toml` and `uv.lock`.
- Remove the active Streamlit entrypoint (`app/streamlit_app.py`) or move it to a clearly marked legacy location that is not part of normal run commands.
- Remove Streamlit-specific run commands from `README.md`, Docker Compose, and other active docs.

### FR-02: Keep FastAPI as the estimator system of record

- The backend must remain runnable on its own with:

```bash
uv run uvicorn app.main:app --reload
```

- Estimation logic must remain behind the existing backend service layer (`app/services/...`), not in route handlers and not in frontend code.
- The frontend must communicate with the backend only through HTTP.

### FR-03: Add an independent web presentation layer

- Create a new `web/` application with its own package manager metadata and dev server commands.
- The frontend must support, at minimum:
  - entering the guided estimation data needed by the current backend contract,
  - submitting requests to the backend,
  - showing loading/submitting state,
  - rendering the estimation result,
  - rendering readable error states.
- The frontend must not import Python modules from `app/` or duplicate estimator business rules.

### FR-03a: Theme appearance (dark / light / system)

- Provide a visible control (for example a toggle, segmented control, or select) to set appearance to **dark**, **light**, or **system**.
- **Default:** **system** — when `system` is selected, the UI follows `prefers-color-scheme` and updates if the OS/browser theme changes while the app is open.
- **Persistence:** Store the selected mode in client-side storage (for example `localStorage`) with a stable key; on first visit with no stored value, use **system**.
- **Consistency:** Light and dark palettes must cover the main surfaces (background, text, inputs, focus states) so the estimation flow remains readable and accessible in both modes.

### FR-04: Preserve and expose the current API contract cleanly

- The migration should reuse the current structured estimation flow already exposed by FastAPI.
- If the frontend uses a simpler form state internally, it must map that state into the backend request payload at the API boundary.
- Validation remains a backend responsibility through Pydantic schemas; frontend validation is only a usability layer.

### FR-05: Enable CORS for local development

- Add `CORSMiddleware` to the FastAPI app.
- Allowed origins must come from typed settings, not hardcoded ad hoc values inside route files.
- Local development must support at least the frontend dev origin used by the new `web/` app.
- Do not use unrestricted `"*"` origins in production-oriented defaults.

### FR-06: Environment-based configuration

- Backend frontend-origin settings must be loaded through `pydantic-settings`.
- Add the new variables to `.env.example` and document them in `README.md`.
- Minimum expected configuration surface:
  - `APP_ENV`
  - `FRONTEND_ORIGINS` (or equivalent typed list setting)
  - existing provider/model settings already required by the backend

### FR-07: Update local developer workflows

- Replace the current two-service (`app` + `streamlit`) local story with a backend + web workflow.
- If Docker Compose remains part of the supported workflow, it must start the new web layer instead of Streamlit.
- README commands must clearly separate backend startup from frontend startup.

## Technical Approach

### Target layout

```text
project-root/
├── app/
│   ├── main.py
│   ├── routers/
│   ├── schemas/
│   └── services/
├── web/
│   ├── package.json
│   └── src/
└── README.md
```

### Backend

- Keep the current FastAPI application in `app/`.
- Add CORS configuration in `app/main.py`, sourcing allowed origins from `app/config.py`.
- Keep route orchestration in `app/routers/estimations.py` and estimation logic in services.
- Avoid changing the request/response contract unless the frontend migration reveals a concrete blocker.

### Frontend

- Create a standalone frontend in `web/` with its own dependencies and scripts.
- Use a small API client module to centralize requests to the FastAPI backend.
- Keep presentation concerns in frontend components/modules: form state, submit lifecycle, loading state, result rendering, and user-safe error messages.
- The exact UI framework is implementation detail, but the app must run independently from the backend runtime and consume the backend over HTTP.
- Theme: implement **dark** / **light** / **system** with default **system**; apply the active palette via a single mechanism the app can reuse (for example a root `class`/`data-theme` attribute, CSS variables, or the stack’s built-in dark-mode support). Listen for `prefers-color-scheme` changes when mode is **system**. Persist non-default and default choices consistently so returning users keep their preference.

## Acceptance Criteria

- [ ] `streamlit` is removed from active project dependencies and no supported run command relies on Streamlit.
- [ ] The backend still starts with `uv run uvicorn app.main:app --reload`.
- [ ] A new `web/` application starts independently and can submit estimation requests to the backend.
- [ ] The browser UI displays successful estimation results without using Streamlit.
- [ ] The backend remains the only place where estimation logic and provider orchestration live.
- [ ] CORS is configured through typed settings and works for local frontend development.
- [ ] `README.md` explains how to run backend and frontend separately.
- [ ] `.env.example` documents any new frontend-origin or web-related backend settings.
- [ ] The web UI exposes a theme control with **dark**, **light**, and **system**; first visit defaults to **system** (no stale storage) and follows OS light/dark until the user changes it.
- [ ] Choosing **dark** or **light** overrides `prefers-color-scheme`; choosing **system** tracks the OS/browser scheme again.
- [ ] The selected theme persists across full page reloads (client-side storage).

## Test Plan

- **Backend unit/integration**
  - Add focused tests for CORS-related settings parsing if new parsing logic is introduced.
  - Keep or update API tests so the existing estimation endpoints still work after Streamlit removal.
- **Frontend**
  - Add frontend tests only if the chosen stack already supports lightweight component/unit testing without large setup overhead.
- **Manual checks**
  - Start backend locally with `uv run uvicorn app.main:app --reload`.
  - Start frontend locally from `web/`.
  - Submit a valid estimation request from the browser and confirm the result is rendered.
  - Confirm a browser-origin request succeeds without CORS errors.
  - Confirm an invalid request shows readable frontend feedback and backend validation still behaves safely.
  - Theme: with no prior site data, confirm default is **system** and UI matches OS light/dark; switch to **dark** and **light** and confirm contrast; reload and confirm persistence; return to **system** and confirm it tracks a simulated OS theme change (devtools or OS toggle).

## Verification

- Pre-implementation: specification only; no code or runtime changes made in this work item.
- Implementation-done evidence for the future task:
  - focused automated checks for backend changes,
  - manual backend + frontend smoke test,
  - updated docs and `.env.example`,
  - no Streamlit runtime left in the supported developer path.

## Documentation Plan

- Update `README.md` to replace Streamlit instructions with backend + web instructions.
- Update `.env.example` with frontend-origin settings required by CORS.
- If Docker workflow remains supported, update Compose documentation accordingly.
- Optionally mention the theme control in README or in-app help only if it aids onboarding (no separate doc required for a small UI preference).
- After implementation, sync the mirrored docs if this work item is authored in the Second Brain first.

## Baby Steps

1. Document the current Streamlit-coupled surface: dependency, Compose service, run commands, and docs references.
2. Add backend CORS settings and wire them in `app/main.py`.
3. Scaffold the independent `web/` app and a minimal API client to the existing estimation endpoint.
4. Recreate the essential Streamlit user flow in the web UI: form, submit, loading, result, and error states; add theme control (**dark** / **light** / **system**, default **system**, persisted).
5. Remove Streamlit runtime pieces and update README / `.env.example` / Compose.
6. Run focused verification and confirm the supported local workflow is now backend + web.

---

## Repository commits (master-ia)

| Short hash | Message | Scope / summary |
|------------|---------|-----------------|
| `e14e563` | `docs(estimador-cag): add feature-010 remove Streamlit work item` | Canonical spec for splitting Streamlit UI from FastAPI: React+Vite+TypeScript, Tailwind, Zod, REST+SSE; Langfuse, PostgreSQL, Redis, and LiteLLM redesign explicitly out of scope. |
| `d5e1286` | `docs(estimador-cag): backfill commit hash in feature-010 work item` | Replace the `pending` placeholder in the commit log with the short hash of the work item document commit. |
| `c444e37` | `feat(api): add configurable CORS for frontend origins` | `Settings.frontend_origins` / `frontend_origins_list()`, `app/cors.py`, wire in `app/main.py`, `.env.example`, tests. |
| `fe31491` | `chore(web): scaffold React Vite TS app with Tailwind and Zod` | `web/` Vite template, Tailwind v4, Vitest config, minimal `App`. |
| `0601b71` | `test(web): add Vitest and SSE stream parser tests` | `sseParser.ts` + tests mirroring Streamlit SSE framing. |
| `9f4b514` | `feat(web): map guided form state to estimation request payload` | Zod `estimationFormSchema`, `mapEstimationFormToRequestBody`, unit tests. |
| `1358ad4` | `feat(web): add estimation streaming UI and API client` | `EstimationWorkbench`, `useEstimateStream`, `estimateApi`, `fileToBase64`, `react-markdown`, `web/nginx/default.conf`. |
| `3e4bfe5` | `chore(docker): serve static web UI and replace Streamlit in compose` | `Dockerfile.web`, `docker-compose.yml` / `docker-compose.dev.yml`, root `Dockerfile` EXPOSE. |
| `472d55e` | `chore!: remove streamlit dependency and demo entrypoint` | Drop `streamlit` from `pyproject.toml` / `uv.lock`; remove `app/streamlit_app.py`, `app/streamlit_error_messages.py`, `tests/test_streamlit_error_messages.py`. |
| `ea6315b` | `docs: document backend-web workflow and CORS settings` | `README.md`, `docs/technical/README.md`, `.env.example`. |
| `f18801c` | `feat(web): add appearance theme system light dark` | `web/src/theme/appearance.ts`, `useAppearance.ts`, `ThemeControl.tsx`, tests; `index.css` `@custom-variant dark`; `index.html` inline theme bootstrap; `App.tsx` toolbar; dual-theme styles + focus rings in `EstimationWorkbench.tsx`; `web/README.md` Appearance section. |
| `39af082` | `docs(cursor): add continue-task and update-feature commands` | Cursor slash commands for resuming implementation from an existing canonical feature doc and for refining `/write-feature` specs in place. |
