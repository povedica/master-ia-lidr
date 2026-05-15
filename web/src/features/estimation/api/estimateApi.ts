/** Centralize FastAPI base URL for browser-side calls. */

export function getApiBaseUrl(): string {
  const raw =
    typeof import.meta.env.VITE_API_BASE_URL === 'string' &&
    import.meta.env.VITE_API_BASE_URL.trim() !== ''
      ? import.meta.env.VITE_API_BASE_URL.trim()
      : 'http://127.0.0.1:8000'
  return raw.replace(/\/$/, '')
}

/** Structured v2 estimate: synchronous JSON ``EstimationResponse`` with ``result``. */
export function estimateStructuredUrl(): string {
  return `${getApiBaseUrl()}/api/v2/estimate`
}
