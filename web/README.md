# Estimator — web UI

React + Vite + TypeScript client for the **session-first simplified estimator**. On load the app creates a session (`POST /api/v1/sessions`), lists recent sessions in a collapsible sidebar (`GET /api/v1/sessions`), and submits the short form to `POST /api/v1/sessions/{session_id}/estimate`. Submits use **JSON** when there are no new files; when the user attaches files, `estimateInSession` sends **`multipart/form-data`** with the same field names as the API. **Project metadata** appears in the right panel (Readable grouped view or **Memory (current)** JSON); the structured **estimate** renders in a full-width panel below.

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
| `npm run test` | Vitest unit tests (`*.test.ts`). |
| `npm run lint` | ESLint. |

## Environment

- **`VITE_API_BASE_URL`** — FastAPI base URL (no trailing slash), e.g. `http://127.0.0.1:8000`. Documented in `.env.example`.

The API must allow this UI’s origin via **`FRONTEND_ORIGINS`** (see repository root `.env.example`).

Run the backend from the repo root:

```bash
uv run uvicorn app.main:app --reload
```

## Appearance

The header includes **System / Light / Dark** theme controls. The choice is stored in **`localStorage`** under key `estimador-cag-appearance` (default **system**). A small inline script in `index.html` applies the class before the first paint to reduce flash.
