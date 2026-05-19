import { getApiBaseUrl } from './estimateApi'

export type SessionCreateResponse = {
  session_id: string
}

export type SessionEstimateResponse = {
  session_id: string
  input_payload: Record<string, unknown>
  project_metadata: Record<string, unknown>
  estimate: Record<string, unknown>
  warnings: string[]
  attachments?: Array<{
    file_id: string
    name: string
    mime_type: string
    status: string
    message?: string | null
  }>
}

export class SessionApiError extends Error {
  readonly status: number
  readonly bodyText: string

  constructor(status: number, bodyText: string) {
    super(`session_api_${status}`)
    this.name = 'SessionApiError'
    this.status = status
    this.bodyText = bodyText
  }
}

export function sessionsUrl(): string {
  return `${getApiBaseUrl()}/api/v1/sessions`
}

export function sessionEstimateUrl(sessionId: string): string {
  return `${getApiBaseUrl()}/api/v1/sessions/${encodeURIComponent(sessionId)}/estimate`
}

export async function createSession(): Promise<SessionCreateResponse> {
  const response = await fetch(sessionsUrl(), {
    method: 'POST',
    headers: { Accept: 'application/json' },
  })
  if (!response.ok) {
    throw new SessionApiError(response.status, await response.text().catch(() => ''))
  }
  return (await response.json()) as SessionCreateResponse
}

export async function estimateInSession(
  sessionId: string,
  body: Record<string, unknown>,
): Promise<SessionEstimateResponse> {
  const response = await fetch(sessionEstimateUrl(sessionId), {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Accept: 'application/json',
    },
    body: JSON.stringify(body),
  })
  const text = await response.text().catch(() => '')
  if (!response.ok) {
    throw new SessionApiError(response.status, text)
  }
  return JSON.parse(text) as SessionEstimateResponse
}
