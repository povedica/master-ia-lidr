import { describe, expect, it } from 'vitest'

import { extractEstimateResult } from './extractEstimateResult'

describe('extractEstimateResult', () => {
  it('returns nested result when present', () => {
    const result = { title: 'Daily Weight Tracker Estimation', totals: { hours: 134 } }
    expect(
      extractEstimateResult({
        result,
        prompt_version: 'estimation/v2',
        mode: 'standard',
      }),
    ).toEqual(result)
  })

  it('returns flat estimate when result is absent but structured fields exist', () => {
    const flat = { title: 'Legacy', phases: [] }
    expect(extractEstimateResult(flat)).toEqual(flat)
  })

  it('unwraps persisted session detail envelope with phases and totals', () => {
    const result = {
      title: 'Portal estimate',
      summary: 'Summary text for the portal effort',
      phases: [{ name: 'Build', items: [{ name: 'Task', hours: 1, cost_eur: 50 }] }],
      totals: { hours: 1, cost_eur: 50 },
      duration_weeks: 1,
      confidence: 0.8,
    }
    expect(
      extractEstimateResult({
        result,
        prompt_version: 'estimation/v2',
        examples_version: 'ex',
        mode: 'standard',
        score: 1,
      }),
    ).toEqual(result)
  })

  it('returns null for envelope-only estimate without result', () => {
    expect(
      extractEstimateResult({
        prompt_version: 'estimation/v2',
        mode: 'standard',
        final_status: 'success',
      }),
    ).toBeNull()
  })

  it('returns null for nullish input', () => {
    expect(extractEstimateResult(null)).toBeNull()
    expect(extractEstimateResult(undefined)).toBeNull()
  })
})
