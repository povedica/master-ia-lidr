import { describe, expect, it } from 'vitest'

import { buildInitialSimplifiedForm } from './simplifiedForm'
import { buildRagQuestion } from './buildRagQuestion'

describe('buildRagQuestion', () => {
  it('combines one-line summary and transcript when both exist', () => {
    const form = {
      ...buildInitialSimplifiedForm(),
      oneLineSummary: 'E-commerce with Stripe',
      transcript: 'Detailed project transcript here.',
    }

    expect(buildRagQuestion(form)).toBe('E-commerce with Stripe\n\nDetailed project transcript here.')
  })

  it('falls back to transcript only', () => {
    const form = {
      ...buildInitialSimplifiedForm(),
      transcript: 'OAuth platform scope',
    }

    expect(buildRagQuestion(form)).toBe('OAuth platform scope')
  })
})
