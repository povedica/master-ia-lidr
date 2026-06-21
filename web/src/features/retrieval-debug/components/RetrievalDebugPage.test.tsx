import { cleanup, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { RetrievalDebugApiError, type RetrievalDebugResponse } from '../api/retrievalDebugApi'

import { RetrievalDebugPage } from './RetrievalDebugPage'

const emptyResponse: RetrievalDebugResponse = {
  query: 'OAuth backend',
  applied_config: {},
  timings_ms: {},
  warnings: [],
  branches: {
    vector: [],
    lexical: null,
    hybrid: null,
    rerank: null,
  },
  final_results: [],
  diff: null,
}

describe('RetrievalDebugPage', () => {
  afterEach(() => {
    cleanup()
  })

  it('renders the idle state before a search runs', () => {
    render(<RetrievalDebugPage />)

    expect(screen.getByText('Run a retrieval debug search to inspect branch rankings.')).toBeTruthy()
  })

  it('disables search while loading', async () => {
    const runDebug = vi.fn(() => new Promise<RetrievalDebugResponse>(() => undefined))
    render(<RetrievalDebugPage runDebug={runDebug} />)

    await userEvent.type(screen.getByLabelText('Query'), 'OAuth backend')
    await userEvent.click(screen.getByRole('button', { name: 'Search' }))

    expect(screen.getByText('Loading retrieval branches...')).toBeTruthy()
    expect(screen.getByRole('button', { name: 'Search' })).toHaveProperty('disabled', true)
  })

  it('renders an empty state when the API returns no final results', async () => {
    render(<RetrievalDebugPage runDebug={vi.fn().mockResolvedValue(emptyResponse)} />)

    await userEvent.type(screen.getByLabelText('Query'), 'OAuth backend')
    await userEvent.click(screen.getByRole('button', { name: 'Search' }))

    expect(await screen.findByText('No retrieval results matched this query.')).toBeTruthy()
  })

  it('renders a friendly API error state', async () => {
    render(
      <RetrievalDebugPage
        runDebug={vi.fn().mockRejectedValue(new RetrievalDebugApiError(503, 'Database is not configured.'))}
      />,
    )

    await userEvent.type(screen.getByLabelText('Query'), 'OAuth backend')
    await userEvent.click(screen.getByRole('button', { name: 'Search' }))

    expect(await screen.findByText('Retrieval debug is temporarily unavailable.')).toBeTruthy()
  })
})
