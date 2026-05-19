import { z } from 'zod'

import { PROJECT_TYPES, TARGET_AUDIENCES, TRANSCRIPT_MAX, TRANSCRIPT_MIN } from './estimationConstants'
import type { AttachmentRefPayload } from './attachmentRefs'

const projectTypeSchema = z.enum(PROJECT_TYPES)
const targetAudienceSchema = z.enum(TARGET_AUDIENCES)

export const simplifiedFormSchema = z
  .object({
    projectName: z.string().trim().min(1, 'Project name is required.').max(120),
    oneLineSummary: z.string().trim().max(200).optional().or(z.literal('')),
    projectType: z.string().min(1, 'Required.'),
    transcript: z
      .string()
      .trim()
      .min(TRANSCRIPT_MIN, `Transcript must be at least ${TRANSCRIPT_MIN} characters.`)
      .max(TRANSCRIPT_MAX),
    targetAudience: z.string().min(1, 'Required.'),
    targetAudienceOther: z.string().trim().max(200).optional().or(z.literal('')),
    industry: z.string().optional().or(z.literal('')),
    additionalExtraInfo: z.string().trim().max(4000).optional().or(z.literal('')),
    attachments: z.array(
      z.object({
        file_id: z.string(),
        name: z.string(),
        mime_type: z.string(),
        content_base64: z.string(),
      }),
    ),
  })
  .superRefine((val, ctx) => {
    if (val.targetAudience === 'other' && !val.targetAudienceOther?.trim()) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        message: 'Audience detail is required when audience is "other".',
        path: ['targetAudienceOther'],
      })
    }
    const typeResult = projectTypeSchema.safeParse(val.projectType)
    if (!typeResult.success) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        message: 'Invalid selection.',
        path: ['projectType'],
      })
    }
    const audienceResult = targetAudienceSchema.safeParse(val.targetAudience)
    if (!audienceResult.success) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        message: 'Invalid selection.',
        path: ['targetAudience'],
      })
    }
  })

export type SimplifiedFormValues = z.infer<typeof simplifiedFormSchema>

export function buildInitialSimplifiedForm(): SimplifiedFormValues {
  return {
    projectName: '',
    oneLineSummary: '',
    projectType: '',
    transcript: '',
    targetAudience: '',
    targetAudienceOther: '',
    industry: '',
    additionalExtraInfo: '',
    attachments: [],
  }
}

export function parseSimplifiedForm(raw: unknown): SimplifiedFormValues {
  return simplifiedFormSchema.parse(raw)
}

export function mapToSessionEstimateBody(values: SimplifiedFormValues): Record<string, unknown> {
  const industry = values.industry?.trim() ? values.industry.trim() : null
  const oneLine = values.oneLineSummary?.trim() ? values.oneLineSummary.trim() : null
  const extra = values.additionalExtraInfo?.trim() ? values.additionalExtraInfo.trim() : null

  return {
    project_name: values.projectName.trim(),
    one_line_summary: oneLine,
    project_type: values.projectType,
    transcript: values.transcript.trim(),
    target_audience: values.targetAudience,
    industry,
    additional_extra_info: extra,
    attachments: values.attachments as AttachmentRefPayload[],
  }
}

function payloadAttachments(payload: Record<string, unknown>): AttachmentRefPayload[] {
  const raw = payload.attachments
  if (!Array.isArray(raw)) {
    return []
  }
  const out: AttachmentRefPayload[] = []
  for (const item of raw) {
    if (!item || typeof item !== 'object') {
      continue
    }
    const row = item as Record<string, unknown>
    const fileId = typeof row.file_id === 'string' ? row.file_id : ''
    const name = typeof row.name === 'string' ? row.name : ''
    const mimeType = typeof row.mime_type === 'string' ? row.mime_type : ''
    const contentBase64 =
      typeof row.content_base64 === 'string' ? row.content_base64 : ''
    if (fileId && name && mimeType && contentBase64) {
      out.push({
        file_id: fileId,
        name,
        mime_type: mimeType,
        content_base64: contentBase64,
      })
    }
  }
  return out
}

/** Restore simplified form fields from a session detail `input_payload`. */
export function payloadToSimplifiedForm(payload: Record<string, unknown> | null): SimplifiedFormValues {
  const base = buildInitialSimplifiedForm()
  if (!payload) {
    return base
  }
  const str = (key: string) => {
    const value = payload[key]
    return typeof value === 'string' ? value : ''
  }
  const industryRaw = payload.industry
  return {
    ...base,
    projectName: str('project_name'),
    oneLineSummary: str('one_line_summary'),
    projectType: str('project_type'),
    transcript: str('transcript'),
    targetAudience: str('target_audience'),
    targetAudienceOther: str('target_audience_other'),
    industry: industryRaw === null || industryRaw === undefined ? '' : String(industryRaw),
    additionalExtraInfo: str('additional_extra_info'),
    attachments: payloadAttachments(payload),
  }
}

/** Field order for focus scroll (top → bottom). */
export const SIMPLIFIED_FORM_FIELD_ORDER: readonly string[] = [
  'projectName',
  'oneLineSummary',
  'projectType',
  'transcript',
  'targetAudience',
  'targetAudienceOther',
  'industry',
  'attachments',
  'additionalExtraInfo',
]
