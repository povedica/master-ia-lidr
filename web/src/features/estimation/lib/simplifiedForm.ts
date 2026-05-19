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
