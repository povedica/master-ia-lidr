import { cleanup, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'

import {
  RetrievalDebugApiError,
  type ChunkInspectionResponse,
  type RetrievalDebugResponse,
} from '../api/retrievalDebugApi'

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

const resultsResponse: RetrievalDebugResponse = {
  ...emptyResponse,
  warnings: [],
  branches: {
    vector: [
      {
        rank: 1,
        chunk_id: 156,
        document_id: 12,
        score: 0.91,
        distance: 0.09,
        matched_terms: [],
      },
    ],
    lexical: null,
    hybrid: [
      {
        rank: 1,
        chunk_id: 156,
        document_id: 12,
        score: 0.6,
        distance: null,
        matched_terms: ['oauth'],
      },
    ],
    rerank: null,
  },
  final_results: [
    {
      final_position: 1,
      chunk_id: 156,
      document_id: 12,
      title: 'OAuth component',
      content_excerpt: 'Backend OAuth implementation',
      semantic_score: 0.91,
      semantic_rank: 1,
      semantic_distance: 0.09,
      lexical_score: null,
      lexical_rank: null,
      fusion_score: 0.6,
      fusion_rank: 1,
      rerank_score: null,
      rerank_rank: null,
      matched_terms: ['oauth'],
      source_strategies: ['vector', 'hybrid'],
      metadata: { component_id: 'AUTH-001' },
      explanation: {
        summary: 'Strong semantic match.',
        signals: ['semantic_strong', 'hybrid_rescued'],
      },
    },
  ],
  diff: {
    common: [],
    vector_only: [],
    lexical_only: [],
    hybrid_rescued: [
      {
        chunk_id: 156,
        document_id: 12,
        source_strategies: ['vector', 'hybrid'],
        branch_ranks: { vector: 1, hybrid: 1 },
      },
    ],
    big_movers: [
      {
        chunk_id: 156,
        document_id: 12,
        from_rank: 3,
        to_rank: 1,
        delta: 2,
      },
    ],
    dropped_by_threshold: [],
    dropped_by_rerank: [],
  },
}

const chunkInspectionResponse: ChunkInspectionResponse = {
  chunk_id: 156,
  document_id: 12,
  content: 'Full backend OAuth implementation chunk.',
  chunk_type: 'budget_component',
  metadata: { component_id: 'AUTH-001' },
  embedding_model: 'text-embedding-3-small',
  embedding_present: true,
  document: { id: 12, source_path: 'data/budgets/example.json' },
  previous_chunk: { content_excerpt: 'Previous context' },
  next_chunk: { content_excerpt: 'Next context' },
  distance: 0.25,
  similarity: 0.75,
  matched_terms: ['oauth', 'backend'],
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
    await userEvent.click(screen.getByLabelText('Enable hybrid'))
    await userEvent.selectOptions(screen.getByLabelText('Hybrid method'), 'weighted')
    await userEvent.clear(screen.getByLabelText('RRF k'))
    await userEvent.type(screen.getByLabelText('RRF k'), '75')
    await userEvent.clear(screen.getByLabelText('Vector weight'))
    await userEvent.type(screen.getByLabelText('Vector weight'), '0.7')
    await userEvent.clear(screen.getByLabelText('Lexical weight'))
    await userEvent.type(screen.getByLabelText('Lexical weight'), '0.3')
    await userEvent.click(screen.getByLabelText('Enable rerank'))
    await userEvent.type(screen.getByLabelText('Document type'), 'historical_budget')
    await userEvent.type(screen.getByLabelText('Client sector'), 'finance')
    await userEvent.type(screen.getByLabelText('Main technology'), 'python')
    await userEvent.type(screen.getByLabelText('Source name'), 'budget_2024_q1')
    await userEvent.type(screen.getByLabelText('Language'), 'en')
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
        enabled: false,
        method: 'weighted',
        rrf_k: 75,
        weights: { vector: 0.7, lexical: 0.3 },
      },
      rerank: { enabled: true },
      filters: {
        document_type: 'historical_budget',
        client_sector: 'finance',
        main_technology: 'python',
        source_name: 'budget_2024_q1',
        language: 'en',
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

  it('renders comparative results, branch rankings, explanations, and ranking diff', async () => {
    render(<RetrievalDebugPage runDebug={vi.fn().mockResolvedValue(resultsResponse)} />)

    await userEvent.type(screen.getByLabelText('Query'), 'OAuth backend')
    await userEvent.click(screen.getByRole('button', { name: 'Search' }))

    expect(await screen.findByText('OAuth component')).toBeTruthy()
    expect(screen.getByText('Backend OAuth implementation')).toBeTruthy()
    expect(screen.getByText('Strong semantic match.')).toBeTruthy()
    expect(screen.getByText('semantic_strong')).toBeTruthy()
    expect(screen.getByText('hybrid_rescued')).toBeTruthy()
    expect(screen.getByText('vector #1')).toBeTruthy()
    expect(screen.getByText('lexical not run')).toBeTruthy()
    expect(screen.getByText('Hybrid rescued')).toBeTruthy()
    expect(screen.getAllByText('chunk 156 / doc 12').length).toBeGreaterThan(0)
    expect(screen.getByText('3 -> 1')).toBeTruthy()
  })

  it('renders warnings as a partial non-blocking state', async () => {
    render(
      <RetrievalDebugPage
        runDebug={vi.fn().mockResolvedValue({
          ...resultsResponse,
          warnings: ['lexical branch failed; showing vector results only'],
        })}
      />,
    )

    await userEvent.type(screen.getByLabelText('Query'), 'OAuth backend')
    await userEvent.click(screen.getByRole('button', { name: 'Search' }))

    expect(await screen.findByText('Partial retrieval results')).toBeTruthy()
    expect(screen.getByText('lexical branch failed; showing vector results only')).toBeTruthy()
  })

  it('renders warnings even when no final results are returned', async () => {
    render(
      <RetrievalDebugPage
        runDebug={vi.fn().mockResolvedValue({
          ...emptyResponse,
          warnings: ['lexical branch failed; no results available'],
        })}
      />,
    )

    await userEvent.type(screen.getByLabelText('Query'), 'OAuth backend')
    await userEvent.click(screen.getByRole('button', { name: 'Search' }))

    expect(await screen.findByText('Partial retrieval results')).toBeTruthy()
    expect(screen.getByText('lexical branch failed; no results available')).toBeTruthy()
  })

  it('opens the chunk inspector drawer from a result row', async () => {
    const inspectChunk = vi.fn().mockResolvedValue(chunkInspectionResponse)
    render(
      <RetrievalDebugPage
        inspectChunk={inspectChunk}
        runDebug={vi.fn().mockResolvedValue(resultsResponse)}
      />,
    )

    await userEvent.type(screen.getByLabelText('Query'), 'OAuth backend')
    await userEvent.click(screen.getByRole('button', { name: 'Search' }))
    await userEvent.click(await screen.findByRole('button', { name: 'Inspect chunk 156' }))

    expect(inspectChunk).toHaveBeenCalledWith(156, 'OAuth backend')
    expect(await screen.findByText('Full backend OAuth implementation chunk.')).toBeTruthy()
    expect(screen.getByText('Previous context')).toBeTruthy()
    expect(screen.getByText('Next context')).toBeTruthy()
    expect(screen.getByText('text-embedding-3-small')).toBeTruthy()
    expect(screen.getByText('oauth, backend')).toBeTruthy()
  })
})
