import { describe, expect, it, vi } from 'vitest'

import type { SessionDetailResponse } from '../api/sessionApi'
import type { PanelStatus } from './useSessionEstimate'
import { applySessionDetailToPanels } from './useSessionEstimate'

function panelSetters() {
  const state = {
    projectMetadata: null as Record<string, unknown> | null,
    metadataStatus: 'empty' as PanelStatus,
    estimate: null as Record<string, unknown> | null,
    estimateStatus: 'empty' as PanelStatus,
    estimateError: null as string | null,
    warnings: [] as string[],
  }
  return {
    state,
    setters: {
      setProjectMetadata: vi.fn((value: Record<string, unknown> | null) => {
        state.projectMetadata = value
      }),
      setMetadataStatus: vi.fn((status: PanelStatus) => {
        state.metadataStatus = status
      }),
      setEstimate: vi.fn((value: Record<string, unknown> | null) => {
        state.estimate = value
      }),
      setEstimateStatus: vi.fn((status: PanelStatus) => {
        state.estimateStatus = status
      }),
      setEstimateError: vi.fn((value: string | null) => {
        state.estimateError = value
      }),
      setWarnings: vi.fn((value: string[]) => {
        state.warnings = value
      }),
    },
  }
}

const baseDetail: SessionDetailResponse = {
  session_id: 'sess-1',
  input_payload: null,
  project_metadata: null,
  estimate: null,
  warnings: [],
  attachments: [],
  submit_count: 0,
}

describe('applySessionDetailToPanels', () => {
  it('restores estimate from persisted v2 envelope', () => {
    const { state, setters } = panelSetters()
    const detail: SessionDetailResponse = {
      ...baseDetail,
      submit_count: 1,
      project_metadata: { project_name: 'Alpha' },
      estimate: {
        result: {
          title: 'Alpha estimate',
          summary: 'x'.repeat(25),
          phases: [],
          totals: { hours: 10, cost_eur: 1000 },
        },
        prompt_version: 'estimation/v2',
      },
      warnings: ['industry was not provided'],
    }

    applySessionDetailToPanels(detail, setters)

    expect(state.metadataStatus).toBe('available')
    expect(state.estimateStatus).toBe('available')
    expect(state.estimate?.title).toBe('Alpha estimate')
    expect(state.warnings).toEqual(['industry was not provided'])
  })

  it('shows error when submit_count > 0 but estimate is missing', () => {
    const { state, setters } = panelSetters()
    applySessionDetailToPanels(
      { ...baseDetail, submit_count: 2, project_metadata: { project_name: 'Beta' } },
      setters,
    )

    expect(state.estimateStatus).toBe('error')
    expect(state.estimateError).toContain('No saved estimate')
  })
})
