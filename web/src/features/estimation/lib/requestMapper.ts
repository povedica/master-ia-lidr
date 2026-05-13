import { z } from 'zod'

const PREPROCESSING = ['none', 'inline_cleaning', 'two_phase'] as const

const PROJECT_TYPES = [
  'web_saas',
  'web_marketing_site',
  'mobile_app',
  'internal_tool',
  'data_pipeline_etl',
  'api_platform',
  'desktop_app',
  'extension_plugin',
  'migration_modernization',
  'other',
] as const

const DELIVERY_URGENCY = ['flexible', 'standard', 'fixed_date', 'critical'] as const

const DATA_SENSITIVITY = [
  'public_only',
  'internal_business',
  'pii_light',
  'pii_heavy',
  'regulated_unknown',
] as const

const INTEGRATION_CATEGORIES = [
  'none',
  'payments',
  'crm',
  'erp',
  'identity_sso',
  'email_notifications',
  'file_storage',
  'analytics_bi',
  'maps_geo',
  'messaging_chat',
  'legacy_db',
  'third_party_api_unknown',
  'other',
] as const

const HOSTING_CONSTRAINTS = [
  'no_preference',
  'cloud_managed',
  'customer_cloud_only',
  'on_prem',
  'air_gapped',
  'hybrid',
] as const

const UI_LANGUAGES = ['en', 'es', 'pt', 'fr', 'de', 'other'] as const

const TARGET_AUDIENCE = [
  'b2c_consumers',
  'b2b_smb',
  'b2b_enterprise',
  'internal_employees',
  'mixed',
  'other',
] as const

const DETAIL_LEVEL = ['summary', 'medium', 'detailed'] as const

const OUTPUT_FORMAT = ['phases_table', 'line_items', 'narrative'] as const

const attachmentSchema = z.object({
  filename: z.string().min(1).max(255),
  content_type: z.enum(['text/plain', 'text/markdown', 'application/pdf']),
  content_base64: z.string().min(1),
})

function nonEmptyLines(blob: string, maxLines?: number): string[] {
  const lines = blob
    .split('\n')
    .map((ln) => ln.trim())
    .filter((ln) => ln.length > 0)
  if (maxLines !== undefined) {
    return lines.slice(0, maxLines)
  }
  return lines
}

export const estimationFormSchema = z
  .object({
    projectName: z.string(),
    projectSummary: z.string().min(20).max(200),
    projectType: z.enum(PROJECT_TYPES),
    targetAudience: z.enum(TARGET_AUDIENCE),
    targetAudienceOther: z.string(),
    industry: z.string(),
    industryOther: z.string(),
    projectDescription: z.string().min(100).max(24_000),
    deliverablesText: z.string().min(1),
    outOfScopeText: z.string(),
    deliveryUrgency: z.enum(DELIVERY_URGENCY),
    targetDate: z.string(),
    deliveryApproach: z.string(),
    integrationCategories: z.array(z.enum(INTEGRATION_CATEGORIES)),
    integrationCustomText: z.string(),
    dataSensitivity: z.enum(DATA_SENSITIVITY),
    hostingConstraints: z.array(z.enum(HOSTING_CONSTRAINTS)),
    hostingNotes: z.string(),
    teamContext: z.string(),
    uiLanguages: z.array(z.enum(UI_LANGUAGES)).max(3),
    riskLevel: z.string(),
    externalDependenciesText: z.string(),
    detailLevel: z.enum(DETAIL_LEVEL),
    outputFormat: z.enum(OUTPUT_FORMAT),
    attachments: z.array(attachmentSchema).max(3),
    preprocessing: z.enum(PREPROCESSING),
    evaluate: z.boolean(),
  })
  .superRefine((val, ctx) => {
    const deliverables = nonEmptyLines(val.deliverablesText)
    if (deliverables.length < 3 || deliverables.length > 8) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        message: 'deliverables must contain between 3 and 8 non-empty lines',
        path: ['deliverablesText'],
      })
    }
    for (const line of deliverables) {
      if (line.length > 80) {
        ctx.addIssue({
          code: z.ZodIssueCode.custom,
          message: 'each deliverable must be at most 80 characters',
          path: ['deliverablesText'],
        })
        break
      }
    }
    if (val.targetAudience === 'other' && !val.targetAudienceOther.trim()) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        message: 'target_audience_other is required when target_audience is other',
        path: ['targetAudienceOther'],
      })
    }
    if (val.industry === 'other' && !val.industryOther.trim()) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        message: 'industry_other is required when industry is other',
        path: ['industryOther'],
      })
    }
    if (
      (val.deliveryUrgency === 'fixed_date' || val.deliveryUrgency === 'critical') &&
      !val.targetDate.trim()
    ) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        message: 'target_date is required when delivery_urgency is fixed_date or critical',
        path: ['targetDate'],
      })
    }
  })

export type EstimationFormValues = z.infer<typeof estimationFormSchema>

export function parseEstimationForm(raw: unknown): EstimationFormValues {
  return estimationFormSchema.parse(raw)
}

function normalizeIntegrationCategories(
  value: EstimationFormValues['integrationCategories'],
): EstimationFormValues['integrationCategories'] {
  if (value.includes('none')) {
    return []
  }
  return value
}

/** Map validated form values to the JSON body expected by ``POST /api/v1/estimate/stream``. */

export function mapEstimationFormToRequestBody(values: EstimationFormValues): Record<string, unknown> {
  const deliverables = nonEmptyLines(values.deliverablesText)
  const outOfScope = nonEmptyLines(values.outOfScopeText, 5)
  const integrationCustomNames = nonEmptyLines(values.integrationCustomText, 3)
  const externalDeps = nonEmptyLines(values.externalDependenciesText, 3)

  const industry = values.industry.trim() ? values.industry : null
  const deliveryApproach = values.deliveryApproach.trim() ? values.deliveryApproach : null
  const teamContext = values.teamContext.trim() ? values.teamContext : null
  const riskLevel = values.riskLevel.trim() ? values.riskLevel : null

  let targetDate: string | null = null
  if (values.deliveryUrgency === 'fixed_date' || values.deliveryUrgency === 'critical') {
    targetDate = values.targetDate.trim() || null
  }

  const raw: Record<string, unknown> = {
    project_name: values.projectName.trim() || null,
    project_summary: values.projectSummary.trim(),
    project_type: values.projectType,
    target_audience: values.targetAudience,
    target_audience_other: values.targetAudienceOther.trim() || null,
    industry,
    industry_other: values.industryOther.trim() || null,
    project_description: values.projectDescription.trim(),
    deliverables,
    out_of_scope: outOfScope.length ? outOfScope : null,
    delivery_urgency: values.deliveryUrgency,
    target_date: targetDate,
    delivery_approach: deliveryApproach,
    integration_categories: normalizeIntegrationCategories(values.integrationCategories),
    integration_custom_names: integrationCustomNames.length ? integrationCustomNames : null,
    data_sensitivity: values.dataSensitivity,
    hosting_constraints: values.hostingConstraints.length ? values.hostingConstraints : null,
    hosting_notes: values.hostingNotes.trim() || null,
    team_context: teamContext,
    ui_languages: values.uiLanguages,
    risk_level: riskLevel,
    external_dependencies: externalDeps.length ? externalDeps : null,
    detail_level: values.detailLevel,
    output_format: values.outputFormat,
    attachments: values.attachments,
    preprocessing: values.preprocessing,
    evaluate: values.evaluate,
  }

  return raw
}
