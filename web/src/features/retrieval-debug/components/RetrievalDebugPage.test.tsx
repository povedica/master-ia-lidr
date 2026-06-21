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
    localStorage.clear()
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

  it('maps strategy, tuning controls, and filters into the request', async () => {
    const runDebug = vi.fn().mockResolvedValue(emptyResponse)
    render(<RetrievalDebugPage runDebug={runDebug} />)

    await userEvent.type(screen.getByLabelText('Query'), 'OAuth backend')
    await userEvent.selectOptions(screen.getByLabelText('Strategy'), 'lexical')
    await userEvent.clear(screen.getByLabelText('Vector top k'))
    await userEvent.type(screen.getByLabelText('Vector top k'), '12')
    await userEvent.clear(screen.getByLabelText('Semantic threshold'))
    await userEvent.type(screen.getByLabelText('Semantic threshold'), '0.42')
    await userEvent.clear(screen.getByLabelText('Lexical top k'))
    await userEvent.type(screen.getByLabelText('Lexical top k'), '8')
    await userEvent.clear(screen.getByLabelText('Max results'))
    await userEvent.type(screen.getByLabelText('Max results'), '7')
    await userEvent.selectOptions(screen.getByLabelText('Hybrid method'), 'weighted')
    await userEvent.clear(screen.getByLabelText('Vector weight'))
    await userEvent.type(screen.getByLabelText('Vector weight'), '0.7')
    await userEvent.clear(screen.getByLabelText('Lexical weight'))
    await userEvent.type(screen.getByLabelText('Lexical weight'), '0.3')
    await userEvent.click(screen.getByLabelText('Enable rerank'))
    await userEvent.type(screen.getByLabelText('Client sector'), 'finance')
    await userEvent.type(screen.getByLabelText('Tags'), 'python, postgres')
    await userEvent.type(screen.getByLabelText('Year from'), '2023')
    await userEvent.type(screen.getByLabelText('Year to'), '2025')

    await userEvent.click(screen.getByRole('button', { name: 'Search' }))

    expect(runDebug).toHaveBeenCalledWith({
      query: 'OAuth backend',
      strategies: ['lexical'],
      vector: { top_k: 12, threshold: 0.42 },
      lexical: { top_k: 8 },
      hybrid: {
        enabled: true,
        method: 'weighted',
        rrf_k: 60,
        weights: { vector: 0.7, lexical: 0.3 },
      },
      rerank: { enabled: true },
      filters: {
        client_sector: 'finance',
        tags: ['python', 'postgres'],
        year: { from: 2023, to: 2025 },
      },
      max_results: 7,
    })
  })

  it('persists recent searches and reuses them on click', async () => {
    const runDebug = vi.fn().mockResolvedValue(emptyResponse)
    const { unmount } = render(<RetrievalDebugPage runDebug={runDebug} />)

    await userEvent.type(screen.getByLabelText('Query'), 'OAuth backend')
    await userEvent.click(screen.getByRole('button', { name: 'Search' }))
    expect(await screen.findByText('No retrieval results matched this query.')).toBeTruthy()
    unmount()

    render(<RetrievalDebugPage runDebug={runDebug} />)
    await userEvent.click(screen.getByRole('button', { name: 'OAuth backend (all)' }))

    expect(screen.getByLabelText('Query')).toHaveProperty('value', 'OAuth backend')
  })
})
