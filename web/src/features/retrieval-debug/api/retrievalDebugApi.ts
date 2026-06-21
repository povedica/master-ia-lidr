import { z } from 'zod'

import { getApiBaseUrl } from '../../estimation/api/estimateApi'

export const retrievalStrategySchema = z.enum(['all', 'vector', 'lexical', 'hybrid', 'rerank'])

export const retrievalYearFilterSchema = z.object({
  from: z.number().int().optional(),
  to: z.number().int().optional(),
})

export const retrievalMetadataFiltersSchema = z.object({
  document_type: z.string().optional(),
  client_sector: z.string().optional(),
  main_technology: z.string().optional(),
  source_name: z.string().optional(),
  language: z.string().optional(),
  tags: z.array(z.string()).optional(),
  year: retrievalYearFilterSchema.optional(),
})

export const retrievalDebugRequestSchema = z.object({
  query: z.string().min(1),
  strategies: z.array(retrievalStrategySchema).min(1),
  vector: z
    .object({
      top_k: z.number().int().min(1).max(50).optional(),
      threshold: z.number().min(0).max(1).nullable().optional(),
    })
    .optional(),
  lexical: z
    .object({
      top_k: z.number().int().min(1).max(50).optional(),
    })
    .optional(),
  hybrid: z
    .object({
      enabled: z.boolean().optional(),
      method: z.enum(['rrf', 'weighted']).optional(),
      rrf_k: z.number().int().min(1).optional(),
      weights: z.record(z.string(), z.number()).nullable().optional(),
    })
    .optional(),
  rerank: z
    .object({
      enabled: z.boolean().optional(),
    })
    .optional(),
  filters: retrievalMetadataFiltersSchema.nullable().optional(),
  max_results: z.number().int().min(1).max(50).optional(),
})

export const branchResultEntrySchema = z.object({
  rank: z.number().int().min(1),
  chunk_id: z.number().int(),
  document_id: z.number().int(),
  score: z.number().min(0).max(1),
  distance: z.number().min(0).nullable().optional(),
  matched_terms: z.array(z.string()),
})

export const branchesContainerSchema = z.object({
  vector: z.array(branchResultEntrySchema).nullable(),
  lexical: z.array(branchResultEntrySchema).nullable(),
  hybrid: z.array(branchResultEntrySchema).nullable(),
  rerank: z.array(branchResultEntrySchema).nullable(),
})

export const resultExplanationSchema = z.object({
  summary: z.string(),
  signals: z.array(z.string()),
})

export const rankingDiffEntrySchema = z.object({
  chunk_id: z.number().int(),
  document_id: z.number().int(),
  source_strategies: z.array(z.string()),
  branch_ranks: z.record(z.string(), z.number().int()),
})

export const rankingMoverSchema = z.object({
  chunk_id: z.number().int(),
  document_id: z.number().int(),
  from_rank: z.number().int().min(1),
  to_rank: z.number().int().min(1),
  delta: z.number().int().min(0),
})

export const rankingDiffSchema = z.object({
  common: z.array(rankingDiffEntrySchema),
  vector_only: z.array(rankingDiffEntrySchema),
  lexical_only: z.array(rankingDiffEntrySchema),
  hybrid_rescued: z.array(rankingDiffEntrySchema),
  big_movers: z.array(rankingMoverSchema),
  dropped_by_threshold: z.array(rankingDiffEntrySchema),
  dropped_by_rerank: z.array(rankingDiffEntrySchema),
})

export const debugResultSchema = z.object({
  final_position: z.number().int().min(1),
  chunk_id: z.number().int(),
  document_id: z.number().int(),
  title: z.string(),
  content_excerpt: z.string(),
  semantic_score: z.number().min(0).max(1).nullable().optional(),
  semantic_rank: z.number().int().min(1).nullable().optional(),
  semantic_distance: z.number().min(0).nullable().optional(),
  lexical_score: z.number().min(0).max(1).nullable().optional(),
  lexical_rank: z.number().int().min(1).nullable().optional(),
  fusion_score: z.number().min(0).max(1).nullable().optional(),
  fusion_rank: z.number().int().min(1).nullable().optional(),
  rerank_score: z.number().min(0).max(1).nullable().optional(),
  rerank_rank: z.number().int().min(1).nullable().optional(),
  matched_terms: z.array(z.string()),
  source_strategies: z.array(z.string()),
  metadata: z.record(z.string(), z.unknown()),
  explanation: resultExplanationSchema,
})

export const retrievalDebugResponseSchema = z.object({
  query: z.string(),
  applied_config: z.record(z.string(), z.unknown()),
  timings_ms: z.record(z.string(), z.number().int()),
  warnings: z.array(z.string()),
  branches: branchesContainerSchema,
  final_results: z.array(debugResultSchema),
  diff: rankingDiffSchema.nullable().optional(),
})

export const chunkInspectionResponseSchema = z.object({
  chunk_id: z.number().int(),
  document_id: z.number().int(),
  content: z.string(),
  chunk_type: z.string(),
  metadata: z.record(z.string(), z.unknown()),
  embedding_model: z.string(),
  embedding_present: z.boolean(),
  document: z.record(z.string(), z.unknown()),
  previous_chunk: z.record(z.string(), z.unknown()).nullable(),
  next_chunk: z.record(z.string(), z.unknown()).nullable(),
  distance: z.number().nullable().optional(),
  similarity: z.number().nullable().optional(),
  matched_terms: z.array(z.string()).default([]),
})

export type RetrievalDebugRequest = z.infer<typeof retrievalDebugRequestSchema>
export type RetrievalDebugResponse = z.infer<typeof retrievalDebugResponseSchema>
export type ChunkInspectionResponse = z.infer<typeof chunkInspectionResponseSchema>

export class RetrievalDebugApiError extends Error {
  readonly status: number
  readonly bodyText: string

  constructor(status: number, bodyText: string) {
    super(`retrieval_debug_api_${status}`)
    this.name = 'RetrievalDebugApiError'
    this.status = status
    this.bodyText = bodyText
  }
}

export function retrievalDebugUrl(): string {
  return `${getApiBaseUrl()}/api/v1/retrieval-debug`
}

export function chunkInspectionUrl(chunkId: number, query?: string): string {
  const url = `${retrievalDebugUrl()}/chunks/${encodeURIComponent(String(chunkId))}`
  const trimmedQuery = query?.trim()
  if (!trimmedQuery) {
    return url
  }
  return `${url}?${new URLSearchParams({ query: trimmedQuery }).toString()}`
}

async function readJsonText(response: Response): Promise<unknown> {
  const text = await response.text().catch(() => '')
  return text ? JSON.parse(text) : null
}

export async function runRetrievalDebug(
  request: RetrievalDebugRequest,
): Promise<RetrievalDebugResponse> {
  const parsedRequest = retrievalDebugRequestSchema.parse(request)
  const response = await fetch(retrievalDebugUrl(), {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Accept: 'application/json',
    },
    body: JSON.stringify(parsedRequest),
  })
  const text = await response.text().catch(() => '')
  if (!response.ok) {
    throw new RetrievalDebugApiError(response.status, text)
  }
  return retrievalDebugResponseSchema.parse(text ? JSON.parse(text) : null)
}

export async function inspectDebugChunk(
  chunkId: number,
  query?: string,
): Promise<ChunkInspectionResponse> {
  const response = await fetch(chunkInspectionUrl(chunkId, query), {
    method: 'GET',
    headers: { Accept: 'application/json' },
  })
  if (!response.ok) {
    throw new RetrievalDebugApiError(response.status, await response.text().catch(() => ''))
  }
  return chunkInspectionResponseSchema.parse(await readJsonText(response))
}
