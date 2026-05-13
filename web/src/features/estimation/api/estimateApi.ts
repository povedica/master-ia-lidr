/** Centralize FastAPI base URL for browser-side calls. */

export function getApiBaseUrl(): string {
  const raw =
    typeof import.meta.env.VITE_API_BASE_URL === 'string' &&
    import.meta.env.VITE_API_BASE_URL.trim() !== ''
      ? import.meta.env.VITE_API_BASE_URL.trim()
      : 'http://127.0.0.1:8000'
  return raw.replace(/\/$/, '')
}

export function estimateStreamUrl(): string {
  return `${getApiBaseUrl()}/api/v1/estimate/stream`
}
