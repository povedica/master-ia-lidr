# Estimador CAG — web UI

React + Vite + TypeScript client for the guided estimation form. It calls **`POST /api/v1/estimate/stream`** on the FastAPI backend and parses SSE (`chunk`, `done`, `error`) in the browser.

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

## Environment

- **`VITE_API_BASE_URL`** — FastAPI base URL (no trailing slash), e.g. `http://127.0.0.1:8000`. Documented in `.env.example`.

The API must allow this UI’s origin via **`FRONTEND_ORIGINS`** (see repository root `.env.example`).
