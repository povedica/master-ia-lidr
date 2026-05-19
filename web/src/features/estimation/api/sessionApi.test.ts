import { afterEach, describe, expect, it, vi } from 'vitest'

import { createSession, estimateInSession, SessionApiError, sessionEstimateUrl, sessionsUrl } from './sessionApi'

describe('sessionApi', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('builds session URLs from API base', () => {
    expect(sessionsUrl()).toMatch(/\/api\/v1\/sessions$/)
    expect(sessionEstimateUrl('sess_abc')).toContain('/api/v1/sessions/sess_abc/estimate')
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
