import { cleanup, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it } from 'vitest'

import type { RagEstimationResponse } from '../api/ragEstimateApi'

import { RagCitationTableView } from './RagCitationTable'

const groundedFixture: RagEstimationResponse = {
  request_id: 'req-1',
  citation_summary: {
    grounded_ok: 1,
    dangling: 0,
    insufficient: 1,
    integrity_violations: 0,
    has_dangling: false,
  },
  result: {
    schema_version: 'rag-1',
    summary: 'Platform estimate with OAuth and payments grounded in retrieved budgets.',
    total_hours: 80,
    currency: 'EUR',
    insufficient_context: false,
    line_items: [
      {
        component: 'authentication',
        hours: 40,
        rationale: 'OAuth2 login and session management from budget evidence.',
        grounded: true,
        sources: [
          {
            chunk_id: 42,
            document_id: 7,
            budget_id: 'BUD-2024-014',
            evidence: 'OAuth2 integration with social providers',
          },
        ],
      },
      {
        component: 'payments',
        hours: 0,
        rationale: 'No supporting chunk for mobile wallet integration.',
        grounded: false,
        sources: [],
      },
    ],
  },
}

afterEach(() => {
  cleanup()
})

describe('RagCitationTableView', () => {
  it('renders grounded line with source evidence', () => {
    render(<RagCitationTableView response={groundedFixture} />)

    expect(screen.getByText('authentication')).toBeTruthy()
    expect(screen.getByText('yes')).toBeTruthy()
    expect(screen.getByText('no')).toBeTruthy()
    expect(screen.getByText(/chunk 42/)).toBeTruthy()
    expect(screen.getByText(/OAuth2 integration with social providers/)).toBeTruthy()
    expect(screen.getByText('Grounded OK')).toBeTruthy()
  })

  it('shows empty state when insufficient context', () => {
    render(
      <RagCitationTableView
        response={{
          ...groundedFixture,
          result: {
            ...groundedFixture.result,
            insufficient_context: true,
            line_items: [],
            total_hours: 0,
          },
        }}
      />,
    )

    expect(screen.getByText(/Insufficient retrieval context/)).toBeTruthy()
  })

  it('expands long rationale on demand', async () => {
    const user = userEvent.setup()
    const longRationale = 'x'.repeat(150)
    render(
      <RagCitationTableView
        response={{
          ...groundedFixture,
          result: {
            ...groundedFixture.result,
            line_items: [
              {
                ...groundedFixture.result.line_items[0],
                rationale: longRationale,
              },
            ],
          },
        }}
      />,
    )

    expect(screen.getByText(`${'x'.repeat(120)}…`)).toBeTruthy()
    await user.click(screen.getByRole('button', { name: 'Show more' }))
    expect(screen.getByText(longRationale)).toBeTruthy()
  })
})
