# Feature: Remove Streamlit and split the demo into Backend API + Web presentation layer

## Objective

Replace the current Streamlit demo with an independent `React + Vite + TypeScript` web frontend that consumes the existing FastAPI backend over HTTP. This feature is intentionally limited to separating the UI from the application logic: the backend remains the single owner of estimation logic, prompt construction, provider orchestration, and response shaping, while the new web layer owns only user interaction and presentation.

## Context

- The repository already has a working FastAPI backend under `app/`, with entrypoint `app/main.py`, router `app/routers/estimations.py`, structured request schema `app/schemas/estimation_request.py`, and service orchestration in `app/services/llm_service.py`.
- The current Streamlit UI lives in `app/streamlit_app.py`, but it already behaves as a client: it sends structured JSON to `POST /api/v1/estimate/stream` over HTTP/SSE and renders the streamed response. This migration should preserve that separation and remove the Streamlit-specific runtime and dependency.
- `pyproject.toml` still includes `streamlit`, and `docker-compose.yml` still starts a `streamlit` service on port `8501`.
- The backend does not currently configure CORS, so a browser frontend hosted on a different origin would fail without explicit origin handling.
- The current public API contract is already centered on the guided-form `EstimationRequest`; this feature should not broaden scope by redesigning the estimation contract unless implementation discovers a blocking issue.

## Scope

### Includes

- Remove Streamlit from the active runtime, dependencies, Compose wiring, and developer documentation.
- Add a new independent frontend under `web/` built with `React + Vite + TypeScript`, `Tailwind CSS`, and `Zod`, talking to the FastAPI backend via HTTP only.
- Keep the backend package under `app/`; do not move estimator logic into the frontend.
- Add backend CORS configuration for local frontend development.
- Preserve the current backend request contract and both estimation endpoints unless a blocking issue is discovered.
- Preserve the current streaming UX using the existing SSE endpoint.
- Update local run instructions so backend and frontend can be started independently.
- Replace the supported Docker Compose workflow so it runs `app` + `web` instead of `app` + `streamlit`.

### Excludes

- No authentication, user accounts, persistence, estimation history, or file storage changes.
- No estimator business-logic redesign, scoring redesign, guardrail redesign, or prompt-contract redesign beyond the refactoring strictly required by the migration.
- No forced API route rename; keep existing endpoints such as `POST /api/v1/estimate` and `POST /api/v1/estimate/stream` unless a follow-up work item explicitly changes them.
- No new alternative streaming endpoint just to support browser APIs; the web app must adapt to the current `POST` SSE contract.
- No routing-heavy SPA architecture, global state framework, design-system rollout, background jobs, Langfuse rollout, LiteLLM redesign, PostgreSQL work, Redis work, or cloud deployment work in this feature.

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

- Create a new `web/` application with `React + Vite + TypeScript`, `Tailwind CSS`, and `Zod`, with its own package metadata and standard scripts such as `dev`, `build`, and `preview`.
- The frontend must support, at minimum:
  - entering the guided estimation data needed by the current backend contract,
  - submitting requests to the backend,
  - streaming progressive output in the browser,
  - showing loading/submitting state,
  - rendering the estimation result,
  - rendering readable error states.
- The frontend must not import Python modules from `app/` or duplicate estimator business rules.
- The first version should stay intentionally small: one main feature screen, no React Router, and no global state library unless implementation reveals a real need.
- `Zod` should be used only for frontend form/input validation and request-shape assistance on the client side; canonical API validation remains in the backend with Pydantic.

### FR-04: Preserve and expose the current API contract cleanly

- The migration should reuse the current structured estimation flow already exposed by FastAPI.
- If the frontend uses a simpler form state internally, it must map that state into the backend request payload at the API boundary.
- Validation remains a backend responsibility through Pydantic schemas; frontend validation is only a usability layer.
- Keep both backend endpoints:
  - `POST /api/v1/estimate` as the stable non-streaming contract for tests, non-interactive clients, and regression checks.
  - `POST /api/v1/estimate/stream` as the primary UI path for progressive rendering.
- The new web UI must work against the current `EstimationRequest` contract without introducing incompatible API changes in this feature.

### FR-05: Enable CORS for local development

- Add `CORSMiddleware` to the FastAPI app.
- Allowed origins must come from typed settings, not hardcoded ad hoc values inside route files.
- Local development must support, at minimum:
  - `http://localhost:5173`
  - `http://127.0.0.1:5173`
- Do not use unrestricted `"*"` origins in production-oriented defaults.
- Default backend behavior should keep `allow_credentials=False` unless a later feature introduces cookie/session requirements.

### FR-06: Environment-based configuration

- Backend frontend-origin settings must be loaded through `pydantic-settings`.
- Add the new variables to `.env.example` and document them in `README.md`.
- Minimum expected configuration surface:
  - `APP_ENV`
  - `FRONTEND_ORIGINS=http://localhost:5173,http://127.0.0.1:5173`
  - existing provider/model settings already required by the backend
- Add frontend environment documentation under `web/` as well:
  - `VITE_API_BASE_URL=http://127.0.0.1:8000`
- The frontend must not contain backend secrets, model identifiers, provider credentials, or duplicated backend settings.
- No observability vendor configuration is introduced in this feature; Langfuse remains a future evolutive.

### FR-07: Update local developer workflows

- Replace the current two-service (`app` + `streamlit`) local story with a backend + web workflow.
- Docker Compose remains part of the supported workflow and must start the new web layer instead of Streamlit.
- README commands must clearly separate backend startup from frontend startup.
- The frontend must be runnable locally from `web/`, and the repository root workflow must remain documented for both local development and Compose.

### FR-08: Preserve streaming behavior in the browser

- The primary browser experience must use `POST /api/v1/estimate/stream`.
- Because the backend stream uses `POST`, the frontend must consume the SSE response with `fetch`/`ReadableStream` parsing rather than `EventSource`.
- The frontend must handle the existing stream event types `chunk`, `done`, and `error`.
- `chunk` events append progressive markdown, `done` closes the loading state and captures final metadata, and `error` renders a readable failure message.

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
│   ├── vite.config.ts
│   ├── tsconfig.json
│   ├── index.html
│   ├── .env.example
│   ├── tailwind.config.ts
│   ├── postcss.config.js
│   └── src/
│       ├── main.tsx
│       ├── App.tsx
│       ├── features/
│       │   └── estimation/
│       │       ├── api/
│       │       │   ├── estimateApi.ts
│       │       │   └── sseParser.ts
│       │       ├── components/
│       │       ├── hooks/
│       │       │   └── useEstimateStream.ts
│       │       ├── lib/
│       │       │   ├── requestMapper.ts
│       │       │   └── fileToBase64.ts
│       │       └── types/
└── README.md
```

### Backend

- Keep the current FastAPI application in `app/`.
- Add CORS configuration in `app/main.py`, sourcing allowed origins from `app/config.py`.
- Keep route orchestration in `app/routers/estimations.py` and estimation logic in services.
- Keep `app/main.py` small; if origin parsing or normalization is needed, keep it in `app/config.py`, not embedded in bootstrap code.
- Avoid changing the request/response contract unless the frontend migration reveals a concrete blocker.
- Keep `POST /api/v1/estimate` and `POST /api/v1/estimate/stream` as-is in this feature.

### Frontend

- Create a standalone `React + Vite + TypeScript` frontend in `web/`.
- Use `Tailwind CSS` for styling the first version of the UI.
- Use `Zod` for frontend-side validation and form schema support.
- Use a small API client module to centralize requests to the FastAPI backend.
- Keep presentation concerns in frontend components/modules: form state, submit lifecycle, loading state, result rendering, and user-safe error messages.
- Implement a reusable `requestMapper` that transforms UI state into the current backend `EstimationRequest` payload.
- Implement a reusable SSE parser for the `POST /api/v1/estimate/stream` response using browser `fetch` streaming.
- Convert attachments to base64 in the browser before sending, while keeping frontend size/type validation only as UX help; canonical validation remains in the backend.
- The frontend must run independently from the backend runtime and consume the backend over HTTP.

### Data flow

1. The user fills the React form with local component state.
2. The frontend maps the form state into the current `EstimationRequest` payload.
3. Optional attachments are converted to base64 in the browser and included in the request body.
4. The UI sends `POST /api/v1/estimate/stream` to the FastAPI backend.
5. The SSE parser handles `chunk`, `done`, and `error` events from the streamed response.
6. The UI renders markdown progressively during streaming and final status/metadata once the stream completes.
7. The non-streaming endpoint remains available for regression checks, curl usage, and non-interactive clients.

## Risks and trade-offs

- **Streaming over `POST`:** browser support requires `fetch` + manual SSE parsing instead of `EventSource`. This adds a small amount of frontend code but avoids redesigning the backend contract.
- **Frontend option duplication:** select options and labels may need a frontend representation. That is acceptable as presentation data, but backend validation and domain rules must remain canonical in `app/`.
- **Attachment handling:** converting files to base64 in the browser is straightforward, but the UI should surface file limits early to avoid poor UX.
- **Compose migration:** replacing `streamlit` with `web` is in scope because Compose is already part of the supported developer workflow. This should be treated as migration work, not as a broader deployment redesign.
- **Scope creep risk:** this feature should not become a redesign of the estimation request, SSE protocol, LiteLLM integration, Langfuse observability, persistence, caching, visual design system, or production deployment.

## Implementation progress

- [x] Step 1–2: `FRONTEND_ORIGINS`, `app/cors.py`, `CORSMiddleware`, tests (`tests/test_cors.py`, `tests/test_config.py`).
- [x] Step 3: `web/` scaffold (Vite, React, TS, Tailwind v4, Zod, Vitest).
- [x] Step 4–5: `estimateApi.ts`, `useEstimateStream.ts`, `sseParser.ts` + tests.
- [x] Step 6: `requestMapper.ts` + Zod + tests.
- [x] Step 7: `EstimationWorkbench.tsx`, `fileToBase64.ts`, progressive markdown via `react-markdown`.
- [x] Step 8: `Dockerfile.web`, `docker-compose.yml` `web` service, `docker-compose.dev.yml` Streamlit removed, `pyproject.toml` / `uv.lock` without Streamlit, deleted `app/streamlit_app.py` and Streamlit-only helpers/tests.
- [x] Step 9: Docs (`README.md`, `docs/technical/README.md`, `.env.example`, `web/README.md`); `docker compose config -q`; `GEMINI_API_KEY= DEFAULT_LLM_PROVIDER=unset uv run pytest` (151 passed).

## Acceptance Criteria

- [x] `streamlit` is removed from active project dependencies and no supported run command relies on Streamlit.
- [x] The backend still starts with `uv run uvicorn app.main:app --reload`.
- [x] A new `web/` application built with `React + Vite + TypeScript`, `Tailwind CSS`, and `Zod` starts independently and can submit estimation requests to the backend.
- [x] The browser UI displays successful estimation results without using Streamlit.
- [x] The browser UI uses `POST /api/v1/estimate/stream` and renders progressive output from `chunk` events.
- [x] The frontend works against the current `EstimationRequest` contract without incompatible changes to `POST /api/v1/estimate` or `POST /api/v1/estimate/stream`.
- [x] The backend remains the only place where estimation logic and provider orchestration live.
- [x] CORS is configured through typed settings and works for local frontend development.
- [x] `FRONTEND_ORIGINS` is documented in `.env.example`, and `VITE_API_BASE_URL` is documented for the frontend.
- [x] `docker-compose.yml` no longer starts Streamlit and instead supports the new `web` frontend.
- [x] `README.md` explains how to run backend and frontend separately.
- [x] Browser-visible validation/provider errors are rendered as readable UI feedback for at least invalid request and backend failure cases.
- [x] No Langfuse, PostgreSQL, Redis, or other evolutive platform work is required to consider this feature done.

## Test Plan

- **Backend unit/integration**
  - Add focused tests for CORS-related settings parsing if new parsing logic is introduced.
  - Add or update a focused CORS check for preflight/headers on estimation routes.
  - Keep or update API tests so `POST /api/v1/estimate` and `POST /api/v1/estimate/stream` still work after Streamlit removal.
- **Frontend**
  - Add focused unit tests for `sseParser.ts`.
  - Add focused unit tests for `requestMapper.ts`, especially for lists, optional fields, and attachment mapping.
- **Manual checks**
  - Start backend locally with `uv run uvicorn app.main:app --reload`.
  - Start frontend locally from `web/`.
  - Submit a valid estimation request from the browser and confirm the result is streamed and rendered progressively.
  - Confirm a browser-origin request succeeds without CORS errors.
  - Confirm an invalid request shows readable frontend feedback and backend validation still behaves safely.
  - Confirm a backend/provider failure surfaces as a readable UI error.
  - Confirm the supported Compose workflow starts backend + web successfully.

## Verification

- **Automated:** `GEMINI_API_KEY= DEFAULT_LLM_PROVIDER=unset uv run pytest` — 151 passed (CORS/settings module tests, existing API tests). `cd web && npm run test` — Vitest (`sseParser`, `requestMapper`). `cd web && npm run build`. `docker compose config -q`.
- **Not verified in this session:** Full `docker compose up --build` image build and browser E2E smoke against live LLM keys; manual checklist in §Test Plan should be run locally before closing the PR.
- **Residual risk:** Local pytest can be sensitive to unrelated exported env vars (e.g. `GEMINI_API_KEY`, `DEFAULT_LLM_PROVIDER`); CI should use a clean env. Compose `web` image bakes `VITE_API_BASE_URL` at build time — override build arg if the published API URL differs.

## Documentation Plan

- Update `README.md` to replace Streamlit instructions with backend + web instructions.
- Update `.env.example` with frontend-origin settings required by CORS.
- Add `web/.env.example` or equivalent frontend environment documentation for `VITE_API_BASE_URL`.
- Update Docker/Compose documentation to replace Streamlit with the new `web` frontend.
- Keep observability, persistence, and caching evolutives documented as future work, not as part of this feature's done criteria.
- After implementation, sync the mirrored docs if this work item is authored in the Second Brain first.

## Baby Steps

1. ~~Document the current Streamlit-coupled surface~~ (superseded by implementation).
2. ~~Define backend `FRONTEND_ORIGINS` settings and wire `CORSMiddleware` in `app/main.py`.~~
3. ~~Scaffold `web/` with `React + Vite + TypeScript`, without routing or global state libraries.~~
4. ~~Implement a minimal frontend API client using `VITE_API_BASE_URL`.~~
5. ~~Implement a reusable SSE parser for `chunk`, `done`, and `error`.~~
6. ~~Implement the minimum guided form and map it to the current `EstimationRequest`.~~
7. ~~Recreate the essential Streamlit user flow in the web UI: submit, streaming output, loading, result, and error states.~~
8. ~~Replace Streamlit in active runtime pieces: dependency graph, Compose, and docs.~~
9. ~~Run focused verification and confirm the supported workflow is now backend + web in both local dev and Compose.~~ (Compose runtime smoke: operator checklist.)

---

## Evolutivo: Validación guiada del formulario (web + API)

> **Nota de contrato:** este evolutivo **cambia límites** respecto a `EstimationRequest` actual (`project_description` hasta 24_000, `project_summary` hasta 200, adjuntos sin imágenes, etc.). Implica **actualizar tests**, **OpenAPI** en `/docs`, y **cualquier cliente** (curl, colecciones) que enviara textos largos. Versionar en el mismo work item para trazabilidad.

### Objective

Endurecer y alinear la validación del formulario de estimación **en el navegador (UX inmediata)** y **en FastAPI (fuente de verdad)** para tipos, enumeraciones, longitudes y adjuntos, usando el patrón estándar **Pydantic en el backend + Zod en el frontend** con **las mismas reglas documentadas** (constantes compartidas por convención o módulo de límites único en Python replicado en TypeScript con pruebas de regresión cruzada donde aplique).

### Context

- Contrato actual: `app/schemas/estimation_request.py` (`EstimationRequest`, `Attachment`, enums `StrEnum`).
- Cliente actual: `web/src/features/estimation/lib/requestMapper.ts` (`estimationFormSchema`, `mapEstimationFormToRequestBody`), `EstimationWorkbench.tsx`, `fileToBase64.ts`.
- Tests existentes: `tests/test_estimation_request.py`, Vitest en `web/src/features/estimation/**/*.test.ts`.

### Scope

#### Includes

- **Selectores y enums:** cualquier campo que en JSON sea un enum / lista de enums debe validarse en cliente con `z.enum` / `z.array(z.enum(...))` **idéntico** al conjunto permitido por Pydantic (`ProjectType`, `DeliveryUrgency`, …); no aceptar strings arbitrarios antes del submit.
- **`project_name`:** opcional; si viene, **longitud máxima 100** caracteres (trim); backend `Field(max_length=100)` y validador de trim coherente con el actual.
- **`project_summary` (resumen de una línea):** **20–250** caracteres tras trim (sustituye el rango 20–200 actual en backend y Zod).
- **`project_description`:** **100–1000** caracteres tras trim (sustituye 100–24_000 actual); el `<textarea>` debe mostrar contador o `maxLength` + validación Zod; backend `Field(min_length=100, max_length=1000)`.
- **`deliverables` (textarea):** contenido completo tras trim con **100–500** caracteres (incluyendo saltos de línea si se cuentan en el límite — definir en implementación una regla única: recomendación **longitud del string completo**); sigue siendo obligatorio obtener **3–8 líneas** no vacías al partir por `\n`; **cada línea** ≤ **80** caracteres (mantener regla de ítem existente) y validar que la composición respeta 100–500 en total (ajustar mensajes de error si hay tensión entre líneas y total — si matemáticamente 8×80 > 500, el validador global 500 prevalece y se documenta).
- **Adjuntos:** admitir **`image/jpeg`** y **`image/png`** además de los tipos actuales (`text/plain`, `text/markdown`, `application/pdf`), hasta **3** ficheros; validación **por MIME declarado** (`content_type` / tipo de fichero en input) y, de forma **recomendada**, comprobación **magic bytes** en backend tras decodificar base64 para reducir spoofing (JPEG/PNG firmas); rechazar extensión `.jpg` con `content_type` incorrecto.
- **Resto de campos (criterio):** reutilizar límites ya definidos en Pydantic donde existan (`target_audience_other`, `industry_other`, listas máx., `hosting_notes`, fechas con `target_date` si urgencia lo exige, exclusividad `integration_categories` con `none`, etc.); reflejarlos en Zod y en mensajes de error legibles en UI.
- **Errores API:** mapear `422` de FastAPI a feedback legible (lista de `detail` ya parcialmente soportado en `useEstimateStream`).

#### Excludes

- No cambiar el contrato SSE ni las rutas `POST /api/v1/estimate` / `estimate/stream`.
- No OCR ni tratamiento de píxeles más allá de validar tipo/tamaño.
- No i18n completo de mensajes (inglés técnico en mensajes de validación es suficiente en v1).

### Functional Requirements

| ID | Requisito |
|----|-----------|
| EV-01 | Los **select** / **multiselect** solo producen valores pertenecientes al enum o lista permitida; Zod rechaza cualquier otro valor antes del mapeo a JSON. |
| EV-02 | `project_name`: máximo **100** caracteres (trim); opcional vacío → `null`. |
| EV-03 | `project_summary`: **20–250** caracteres (trim). |
| EV-04 | `project_description`: **100–1000** caracteres (trim). |
| EV-05 | `deliverablesText`: **100–500** caracteres (trim del bloque); **3–8** líneas no vacías; cada línea ≤ **80** caracteres; validación coherente en `@field_validator` / `model_validator` en Pydantic y en Zod. |
| EV-06 | Adjuntos: tipos MIME permitidos incluyen **`image/jpeg`**, **`image/png`**, más los existentes; tamaño máximo por fichero y total según constantes actuales (`_MAX_ATTACHMENT_BYTES`, `_MAX_ATTACHMENTS_TOTAL_BYTES`); input `accept` alineado. |
| EV-07 | Backend: toda regla nueva o ajustada vive en **`app/schemas/estimation_request.py`** (o módulo `app/schemas/estimation_limits.py` extraído si reduce duplicación); sin lógica de negocio nueva en routers. |
| EV-08 | Frontend: esquema Zod único (o módulo `limits.ts` importado por el schema) alineado con los números del backend; **contadores** opcionales pero recomendados en textareas críticos. |

### Technical Approach

1. **Backend (fuente de verdad):** centralizar constantes (`_PROJECT_NAME_MAX = 100`, `_PROJECT_SUMMARY_MAX = 250`, `_PROJECT_DESCRIPTION_MAX = 1000`, límites del textarea de deliverables, `_ATTACHMENT_ALLOWED_TYPES` ampliado). Ajustar `Field` y validadores de `EstimationRequest` / `Attachment`; ampliar tests en `tests/test_estimation_request.py` y fixtures en `tests/estimation_fixtures.py` que asuman longitudes antiguas.
2. **Frontend:** actualizar `estimationFormSchema` y `mapEstimationFormToRequestBody`; `fileToBase64.ts` / input `accept` para imágenes; `EstimationWorkbench` con `maxLength` / `pattern` HTML5 donde ayude sin contradecir Zod.
3. **Técnica estándar:** Pydantic v2 + Zod; sin generador de código obligatorio en v1; **tabla de límites** en este documento y en `docs/technical/README.md` / OpenAPI actualizados al cerrar.
4. **Paridad:** añadir tests que fallen si el backend acepta lo que el frontend rechaza (payloads límite en pytest); Vitest para límites de strings y tipos MIME en el cliente.

### Acceptance Criteria

- [ ] Los enums del formulario web coinciden con los `StrEnum` del backend; valores inválidos no se envían.
- [ ] `project_name`, `project_summary`, `project_description`, bloque `deliverables` cumplen los rangos indicados en backend y frontend.
- [ ] Adjuntos JPEG/PNG aceptados por API y validados por MIME (y magic bytes si se implementa); rechazo claro si el tipo no coincide.
- [ ] `POST /api/v1/estimate` y `POST /api/v1/estimate/stream` devuelven `422` con detalle Pydantic para cuerpos fuera de rango; la UI muestra el error de forma legible.
- [ ] `uv run pytest` y `cd web && npm run test && npm run build` pasan tras los cambios.
- [ ] Documentación técnica y ejemplo curl en README o `docs/technical` reflejan los nuevos límites.

### Test Plan

- **Unit (Python):** límites de longitud, deliverables 100–500 + 3–8 líneas + 80 por línea, adjuntos image/jpeg y image/png válidos e inválidos (tipo incorrecto, tamaño).
- **Unit (Vitest):** mismos casos límite en `requestMapper` / schema; ficheros mock con tipo MIME.
- **Manual:** enviar formulario al límite superior/inferior; adjuntar PNG/JPEG; verificar 422 con payload antiguo (descripción > 1000 chars) rechazado.

### Documentation Plan

- Actualizar `docs/technical/README.md` (contrato JSON / adjuntos).
- Actualizar `README.md` si el ejemplo `curl` usa textos que ya no cumplen límites.
- Actualizar colecciones bajo `api-collection/` si incluyen cuerpos desactualizados.

### Baby Steps (implementación sugerida)

1. Extraer o ajustar constantes y Pydantic en `app/schemas/estimation_request.py`; pytest en rojo/verde.
2. Alinear `tests/estimation_fixtures.py` y tests API que construyan cuerpos.
3. Alinear Zod + mapper + `fileToBase64` + UI (`EstimationWorkbench`); Vitest.
4. Documentación + smoke manual; fila en **Repository commits** cuando se fusione.

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
