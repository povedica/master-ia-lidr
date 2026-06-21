import { afterEach, describe, expect, it, vi } from 'vitest'

import {
  chunkInspectionUrl,
  inspectDebugChunk,
  RetrievalDebugApiError,
  retrievalDebugResponseSchema,
  retrievalDebugUrl,
  runRetrievalDebug,
} from './retrievalDebugApi'

const debugResponse = {
  query: 'OAuth backend',
  applied_config: {
    strategies: ['all'],
    filters: { client_sector: 'finance' },
  },
  timings_ms: { vector: 12, lexical: 9 },
  warnings: ['rerank is a no-op placeholder'],
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
    hybrid: null,
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
      fusion_score: null,
      fusion_rank: null,
      rerank_score: null,
      rerank_rank: null,
      matched_terms: [],
      source_strategies: ['vector'],
      metadata: { component_id: 'AUTH-001' },
      explanation: {
        summary: 'Strong semantic match.',
        signals: ['semantic_strong'],
      },
    },
  ],
  diff: null,
}

const chunkResponse = {
  chunk_id: 156,
  document_id: 12,
  content: 'Backend OAuth implementation',
  chunk_type: 'budget_component',
  metadata: { component_id: 'AUTH-001' },
  embedding_model: 'text-embedding-3-small',
  embedding_present: true,
  document: {
    id: 12,
    source_path: 'data/budgets/example.json',
  },
  previous_chunk: { chunk_id: 155, content_excerpt: 'Previous context' },
  next_chunk: { chunk_id: 157, content_excerpt: 'Next context' },
  distance: 0.25,
  similarity: 0.75,
}

describe('retrievalDebugApi', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('builds debug and chunk inspection URLs from the API base', () => {
    expect(retrievalDebugUrl()).toMatch(/\/api\/v1\/retrieval-debug$/)
    expect(chunkInspectionUrl(156, 'OAuth backend')).toContain(
      '/api/v1/retrieval-debug/chunks/156?query=OAuth+backend',
    )
  })

  it('validates retrieval debug responses with Zod', () => {
    const parsed = retrievalDebugResponseSchema.parse(debugResponse)
    expect(parsed.final_results[0]?.explanation.signals).toEqual(['semantic_strong'])
  })

  it('posts a retrieval debug request and parses the response', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      text: async () => JSON.stringify(debugResponse),
    })
    vi.stubGlobal('fetch', fetchMock)

    const result = await runRetrievalDebug({
      query: 'OAuth backend',
      strategies: ['all'],
      filters: { client_sector: 'finance' },
    })

    expect(result.warnings).toEqual(['rerank is a no-op placeholder'])
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringMatching(/\/api\/v1\/retrieval-debug$/),
      expect.objectContaining({
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
        body: JSON.stringify({
          query: 'OAuth backend',
          strategies: ['all'],
          filters: { client_sector: 'finance' },
        }),
      }),
    )
  })

  it('loads and parses chunk inspection details', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        text: async () => JSON.stringify(chunkResponse),
      }),
    )

    const result = await inspectDebugChunk(156, 'OAuth backend')

    expect(result.previous_chunk?.content_excerpt).toBe('Previous context')
    expect(result.similarity).toBe(0.75)
  })

  it('throws RetrievalDebugApiError for non-ok responses', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: false,
        status: 503,
        text: async () => 'Database is not configured.',
      }),
    )

    await expect(runRetrievalDebug({ query: 'OAuth backend', strategies: ['vector'] })).rejects.toBeInstanceOf(
      RetrievalDebugApiError,
    )
  })
})
