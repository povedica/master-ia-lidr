import { z } from 'zod'

import { getApiBaseUrl } from './estimateApi'

export const sourceReferenceSchema = z.object({
  chunk_id: z.number().int().min(1),
  document_id: z.number().int().min(1),
  budget_id: z.string().nullable().optional(),
  evidence: z.string().min(1),
})

export const ragEstimationLineItemSchema = z.object({
  component: z.string(),
  hours: z.number(),
  rationale: z.string(),
  grounded: z.boolean(),
  sources: z.array(sourceReferenceSchema),
})

export const ragEstimationResultSchema = z.object({
  schema_version: z.string(),
  summary: z.string(),
  line_items: z.array(ragEstimationLineItemSchema),
  total_hours: z.number(),
  currency: z.string(),
  insufficient_context: z.boolean(),
})

export const citationSummarySchema = z.object({
  grounded_ok: z.number().int(),
  dangling: z.number().int(),
  insufficient: z.number().int(),
  integrity_violations: z.number().int(),
  has_dangling: z.boolean(),
})

export const ragEstimationResponseSchema = z.object({
  result: ragEstimationResultSchema,
  citation_summary: citationSummarySchema,
  request_id: z.string(),
  model: z.string().nullable().optional(),
  provider: z.string().nullable().optional(),
  latency_ms: z.number().int().nullable().optional(),
})

export const ragEstimateRequestSchema = z.object({
  question: z.string().min(1),
  mode: z.enum(['A', 'B', 'C', 'D']).optional(),
})

export type RagEstimationResponse = z.infer<typeof ragEstimationResponseSchema>
export type RagEstimationResult = z.infer<typeof ragEstimationResultSchema>
export type CitationSummary = z.infer<typeof citationSummarySchema>
export type RagEstimateRequest = z.infer<typeof ragEstimateRequestSchema>

export class RagEstimateApiError extends Error {
  readonly status: number
  readonly bodyText: string

  constructor(status: number, bodyText: string) {
    super(`rag_estimate_api_${status}`)
    this.name = 'RagEstimateApiError'
    this.status = status
    this.bodyText = bodyText
  }
}

export function ragEstimateUrl(): string {
  return `${getApiBaseUrl()}/api/v1/estimate/rag`
}

export function isRagEstimationResponse(value: unknown): value is RagEstimationResponse {
  return ragEstimationResponseSchema.safeParse(value).success
}

export function isRagEstimationResult(value: unknown): value is RagEstimationResult {
  return ragEstimationResultSchema.safeParse(value).success
}

export async function runRagEstimate(request: RagEstimateRequest): Promise<RagEstimationResponse> {
  const parsedRequest = ragEstimateRequestSchema.parse(request)
  const response = await fetch(ragEstimateUrl(), {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Accept: 'application/json',
    },
    body: JSON.stringify(parsedRequest),
  })
  const text = await response.text().catch(() => '')
  if (!response.ok) {
    throw new RagEstimateApiError(response.status, text)
  }
  return ragEstimationResponseSchema.parse(text ? JSON.parse(text) : null)
}
