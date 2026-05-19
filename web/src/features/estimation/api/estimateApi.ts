/** Centralize FastAPI base URL for browser-side calls. */

/** FastAPI base URL. Empty string = same-origin (Vite/nginx proxy to the API). */
export function getApiBaseUrl(): string {
  const raw =
    typeof import.meta.env.VITE_API_BASE_URL === 'string'
      ? import.meta.env.VITE_API_BASE_URL.trim()
      : ''
  return raw.replace(/\/$/, '')
}
