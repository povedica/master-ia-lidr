# Estimator — web UI

React + Vite + TypeScript client for the **session-first simplified estimator**. On load the app creates a session (`POST /api/v1/sessions`), lists recent sessions in a collapsible sidebar (`GET /api/v1/sessions`), and submits the short form to `POST /api/v1/sessions/{session_id}/estimate`. Submits use **JSON** when there are no new files; when the user attaches files, `estimateInSession` sends **`multipart/form-data`** with the same field names as the API. **Project metadata** appears in the right panel (Readable grouped view or **Memory (current)** JSON); the structured **estimate** renders in a full-width panel below.

## Grounded RAG citations (feature-052)

The estimate result panel exposes **Run RAG estimate**, which posts to `POST /api/v1/estimate/rag` with the one-line summary + transcript as the question (`web/src/features/estimation/api/ragEstimateApi.ts`). The **RAG citations** tab renders `RagCitationTable` / `RagCitationSummary`: per-line `component`, `hours`, `grounded`, `rationale`, `sources[]`, and `citation_summary` counts. This is additive to the CAG v2 session estimate path.

Requires the same populated Postgres corpus as retrieval eval and a running API (`uv run uvicorn app.main:app --reload`).

## Setup

```bash
cp .env.example .env.local
npm install
```

## Scripts

| Command | Purpose |
|--------|---------|
| `npm run dev` | Vite dev server (default `http://127.0.0.1:5173`). |
| `npm run build` | Typecheck + production bundle to `dist/`. |
| `npm run preview` | Serve the production build locally. |
| `npm run test` | Vitest unit/component tests (`*.test.ts` and `*.test.tsx`). |
| `npm run lint` | ESLint. |

## Environment

- **`VITE_API_BASE_URL`** — FastAPI base URL (no trailing slash), e.g. `http://127.0.0.1:8000`. Documented in `.env.example`.
- **`VITE_ENABLE_RETRIEVAL_DEBUG`** — set to `true` to expose the internal `/debug/retrieval` screen. Keep `false` for normal end-user builds.

The API must allow this UI’s origin via **`FRONTEND_ORIGINS`** (see repository root `.env.example`).

Run the backend from the repo root:

```bash
uv run uvicorn app.main:app --reload
```

## Internal retrieval debug screen

The debug screen is intentionally hidden unless `VITE_ENABLE_RETRIEVAL_DEBUG=true`.
It consumes `POST /api/v1/retrieval-debug` and `GET /api/v1/retrieval-debug/chunks/{id}` to compare vector, lexical, hybrid, and rerank lanes, tune request knobs, inspect ranking diffs, and open chunk context in a drawer with distance, similarity, and lexical `matched_terms` when a query is provided.

```bash
cd web
VITE_ENABLE_RETRIEVAL_DEBUG=true npm run dev
# Open http://127.0.0.1:5173/debug/retrieval
```

For Docker Compose, the flag is baked into the nginx-served static bundle at build time:

```bash
VITE_ENABLE_RETRIEVAL_DEBUG=true docker compose up -d --build web
# Open http://127.0.0.1:5175/debug/retrieval
```

## Appearance

The header includes **System / Light / Dark** theme controls. The choice is stored in **`localStorage`** under key `estimador-cag-appearance` (default **system**). A small inline script in `index.html` applies the class before the first paint to reduce flash.
