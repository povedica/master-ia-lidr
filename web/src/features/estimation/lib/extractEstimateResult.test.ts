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
