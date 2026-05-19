import { afterEach, describe, expect, it, vi } from 'vitest'

import {
  createSession,
  estimateInSession,
  getSession,
  listSessions,
  SessionApiError,
  sessionDetailUrl,
  sessionEstimateUrl,
  sessionsUrl,
} from './sessionApi'

describe('sessionApi', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('builds session URLs from API base', () => {
    expect(sessionsUrl()).toMatch(/\/api\/v1\/sessions$/)
    expect(sessionDetailUrl('sess_abc')).toMatch(/\/api\/v1\/sessions\/sess_abc$/)
    expect(sessionEstimateUrl('sess_abc')).toContain('/api/v1/sessions/sess_abc/estimate')
  })

  it('listSessions parses session rows', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({
          sessions: [
            {
              session_id: 'sess_a',
              label: 'Alpha',
              updated_at: '2026-05-19T10:00:00Z',
              submit_count: 1,
            },
          ],
        }),
      }),
    )
    const result = await listSessions()
    expect(result.sessions[0]?.label).toBe('Alpha')
  })

  it('getSession parses detail snapshot', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        text: async () =>
          JSON.stringify({
            session_id: 'sess_a',
            input_payload: { project_name: 'Alpha' },
            project_metadata: { project_name: 'Alpha' },
            estimate: {
              result: { title: 'Alpha estimate', summary: 'x'.repeat(25), totals: { hours: 1, cost_eur: 1 } },
            },
            warnings: [],
            attachments: [],
            submit_count: 1,
          }),
      }),
    )
    const result = await getSession('sess_a')
    expect(result.input_payload?.project_name).toBe('Alpha')
    expect(result.project_metadata?.project_name).toBe('Alpha')
  })

  it('createSession returns session_id on 201', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({ session_id: 'sess_test_1' }),
      }),
    )
    const result = await createSession()
    expect(result.session_id).toBe('sess_test_1')
  })

  it('createSession throws SessionApiError when not ok', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: false,
        status: 503,
        text: async () => 'unavailable',
      }),
    )
    await expect(createSession()).rejects.toBeInstanceOf(SessionApiError)
  })

  it('estimateInSession uses FormData when files are provided', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      text: async () =>
        JSON.stringify({
          session_id: 'sess_test_1',
          input_payload: {},
          project_metadata: {},
          estimate: {},
          warnings: [],
        }),
    })
    vi.stubGlobal('fetch', fetchMock)
    const file = new File(['hello'], 'notes.txt', { type: 'text/plain' })
    await estimateInSession(
      'sess_test_1',
      {
        project_name: 'Neo',
        project_type: 'web_saas',
        target_audience: 'b2b_smb',
        transcript: 'y'.repeat(80),
      },
      { files: [file] },
    )
    const init = fetchMock.mock.calls[0]?.[1] as RequestInit
    expect(init.body).toBeInstanceOf(FormData)
    expect(init.headers).toEqual({ Accept: 'application/json' })
  })

  it('estimateInSession parses envelope on success', async () => {
    const envelope = {
      session_id: 'sess_test_1',
      input_payload: { project_name: 'Neo' },
      project_metadata: { summary: 'x' },
      estimate: { title: 'Estimate' },
      warnings: ['missing urgency'],
    }
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        text: async () => JSON.stringify(envelope),
      }),
    )
    const result = await estimateInSession('sess_test_1', { transcript: 'y'.repeat(80) })
    expect(result.project_metadata).toEqual({ summary: 'x' })
    expect(result.warnings).toEqual(['missing urgency'])
  })
})
