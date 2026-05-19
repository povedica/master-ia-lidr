import { getApiBaseUrl } from './estimateApi'

export type SessionCreateResponse = {
  session_id: string
}

export type SessionListItem = {
  session_id: string
  label: string
  updated_at: string
  submit_count: number
}

export type SessionListResponse = {
  sessions: SessionListItem[]
}

export type SessionDetailResponse = {
  session_id: string
  input_payload: Record<string, unknown> | null
  project_metadata: Record<string, unknown> | null
  estimate: Record<string, unknown> | null
  warnings: string[]
  attachments: Array<{
    file_id: string
    name: string
    mime_type: string
    status: string
    message?: string | null
  }>
  submit_count: number
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

export function sessionDetailUrl(sessionId: string): string {
  return `${getApiBaseUrl()}/api/v1/sessions/${encodeURIComponent(sessionId)}`
}

export function sessionEstimateUrl(sessionId: string): string {
  return `${sessionDetailUrl(sessionId)}/estimate`
}

export async function listSessions(): Promise<SessionListResponse> {
  const response = await fetch(sessionsUrl(), {
    method: 'GET',
    headers: { Accept: 'application/json' },
  })
  if (!response.ok) {
    throw new SessionApiError(response.status, await response.text().catch(() => ''))
  }
  return (await response.json()) as SessionListResponse
}

export async function getSession(sessionId: string): Promise<SessionDetailResponse> {
  const response = await fetch(sessionDetailUrl(sessionId), {
    method: 'GET',
    headers: { Accept: 'application/json' },
  })
  const text = await response.text().catch(() => '')
  if (!response.ok) {
    throw new SessionApiError(response.status, text)
  }
  return JSON.parse(text) as SessionDetailResponse
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

export type EstimateInSessionOptions = {
  /** When set, submit as multipart/form-data (field name `attachments` per file). */
  files?: File[]
}

function appendFormFields(form: FormData, body: Record<string, unknown>): void {
  for (const [key, value] of Object.entries(body)) {
    if (key === 'attachments' || value === null || value === undefined) {
      continue
    }
    if (typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean') {
      form.append(key, String(value))
    }
  }
}

export async function estimateInSession(
  sessionId: string,
  body: Record<string, unknown>,
  options?: EstimateInSessionOptions,
): Promise<SessionEstimateResponse> {
  const files = options?.files ?? []
  let response: Response
  if (files.length > 0) {
    const form = new FormData()
    appendFormFields(form, body)
    for (const file of files) {
      form.append('attachments', file)
    }
    response = await fetch(sessionEstimateUrl(sessionId), {
      method: 'POST',
      headers: { Accept: 'application/json' },
      body: form,
    })
  } else {
    response = await fetch(sessionEstimateUrl(sessionId), {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Accept: 'application/json',
      },
      body: JSON.stringify(body),
    })
  }
  const text = await response.text().catch(() => '')
  if (!response.ok) {
    throw new SessionApiError(response.status, text)
  }
  return JSON.parse(text) as SessionEstimateResponse
}
