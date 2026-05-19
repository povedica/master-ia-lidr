import type { ZodIssue } from 'zod'

export const CUSTOM_INTEGRATIONS_MESSAGE =
  'Each non-empty line must be between 20 and 300 characters.'

/** Shown when 422 maps to one or more fields (optional amber banner). */
export const VALIDATION_SUMMARY_BANNER = 'Please review the fields highlighted in red.'

/** Generic copy when a backend field is known but the rule is not mapped. */
export const GENERIC_FIELD_MESSAGE = 'Please review this field.'

export type ParsedEstimateFailure =
  | { kind: 'validation'; fieldErrors: Record<string, string>; formSummary?: string }
  | { kind: 'generic'; message: string }

/** Maps EstimationRequest / FastAPI `loc` segments to EstimationWorkbench UI keys. */
export const BACKEND_FIELD_TO_UI: Record<string, string> = {
  project_name: 'projectName',
  one_line_summary: 'oneLineSummary',
  transcript: 'transcript',
  additional_extra_info: 'additionalExtraInfo',
  project_summary: 'projectSummary',
  project_type: 'projectType',
  target_audience: 'targetAudience',
  target_audience_other: 'targetAudienceOther',
  project_description: 'projectDescription',
  deliverables: 'deliverablesText',
  delivery_urgency: 'deliveryUrgency',
  target_date: 'targetDate',
  data_sensitivity: 'dataSensitivity',
  detail_level: 'detailLevel',
  output_format: 'outputFormat',
  attachments: 'attachments',
  out_of_scope: 'outOfScopeText',
  delivery_approach: 'deliveryApproach',
  integration_categories: 'integrationCategories',
  integration_custom_names: 'integrationCustomText',
  industry: 'industry',
  industry_other: 'industryOther',
  hosting_constraints: 'hostingConstraints',
  hosting_notes: 'hostingNotes',
  team_context: 'teamContext',
  ui_languages: 'uiLanguages',
  risk_level: 'riskLevel',
  external_dependencies: 'externalDependenciesText',
  preprocessing: 'preprocessing',
  evaluate: 'evaluate',
}

const DELIVERABLES_COUNT_MESSAGE = 'Add between 3 and 8 deliverables, one per line.'
const DELIVERABLE_LINE_MAX_MESSAGE = 'Each deliverable must be at most 80 characters.'
const SELECT_REQUIRED_MESSAGE = 'Required.'
const SELECT_INVALID_MESSAGE = 'Invalid selection.'
const TARGET_DATE_REQUIRED_MESSAGE = 'Please pick a target date for this urgency level.'
const PROJECT_SUMMARY_LENGTH_MESSAGE =
  'One-line summary must be between 20 and 200 characters after trimming leading and trailing spaces.'
const PROJECT_DESCRIPTION_LENGTH_MESSAGE =
  'Project description must be between 100 and 24,000 characters after trimming leading and trailing spaces.'
const PROJECT_NAME_MAX_MESSAGE = 'Project name must be at most 120 characters.'
const HOSTING_NOTES_MAX_MESSAGE = 'Hosting notes must be at most 200 characters.'
const INDUSTRY_OTHER_REQUIRED_MESSAGE = 'Please add industry details when you select "other".'
const TARGET_AUDIENCE_OTHER_REQUIRED_MESSAGE = 'Please add audience details when you select "other".'
const INTEGRATION_NONE_EXCLUSIVE_MESSAGE =
  'If you select "none" for integrations, it cannot be combined with other categories.'
const INTEGRATION_CUSTOM_COUNT_MESSAGE = 'At most 3 custom integrations (one per line).'
const EXTERNAL_DEP_COUNT_MESSAGE = 'At most 3 external dependencies (one per line).'
const EXTERNAL_DEP_LINE_MAX_MESSAGE = 'Each external dependency line must be at most 100 characters.'
const OUT_OF_SCOPE_COUNT_MESSAGE = 'At most 5 out-of-scope lines.'
const OUT_OF_SCOPE_LINE_MAX_MESSAGE = 'Each out-of-scope line must be at most 80 characters.'
const ATTACHMENTS_COUNT_MESSAGE = 'At most 3 attachments.'
const ATTACHMENTS_TOTAL_SIZE_MESSAGE = 'Total decoded attachment size exceeds the allowed limit.'
const ATTACHMENT_ITEM_MESSAGE = 'Please check the attachment (name, type, or base64 content).'
const PREPROCESSING_INVALID_MESSAGE = 'Please select a valid preprocessing option.'

function firstMappedBackendField(loc: readonly unknown[]): string | null {
  for (const part of loc) {
    if (typeof part === 'string' && part in BACKEND_FIELD_TO_UI) {
      return part
    }
  }
  return null
}

function uiKeyForBackendField(backendField: string): string {
  return BACKEND_FIELD_TO_UI[backendField] ?? backendField
}

/** Infer backend field from Pydantic / FastAPI English messages when `loc` is only `body`. */
function inferBackendFieldFromMessage(msg: string): string | null {
  const lower = msg.toLowerCase()
  const hints: [string, string][] = [
    ['integration_custom_names', 'integration_custom_names'],
    ['industry_other', 'industry_other'],
    ['target_audience_other', 'target_audience_other'],
    ['target_date', 'target_date'],
    ['deliverables', 'deliverables'],
    ['out_of_scope', 'out_of_scope'],
    ['external_dependencies', 'external_dependencies'],
    ['integration_categories', 'integration_categories'],
    ['project_summary', 'project_summary'],
    ['project_description', 'project_description'],
    ['attachments', 'attachments'],
    ['at most 3 attachments', 'attachments'],
    ['total decoded attachment', 'attachments'],
  ]
  for (const [needle, field] of hints) {
    if (lower.includes(needle)) {
      return field
    }
  }
  return null
}

function humanMessageForBackendField(backendField: string, rawMsg: string): string {
  const msg = rawMsg.toLowerCase()

  switch (backendField) {
    case 'integration_custom_names':
      if (msg.includes('entries') && msg.includes('at most')) {
        return INTEGRATION_CUSTOM_COUNT_MESSAGE
      }
      if (msg.includes('empty')) {
        return CUSTOM_INTEGRATIONS_MESSAGE
      }
      return CUSTOM_INTEGRATIONS_MESSAGE
    case 'deliverables':
      if (msg.includes('between') || msg.includes('3') || msg.includes('8')) {
        return DELIVERABLES_COUNT_MESSAGE
      }
      if (msg.includes('80') || msg.includes('at most')) {
        return DELIVERABLE_LINE_MAX_MESSAGE
      }
      return DELIVERABLES_COUNT_MESSAGE
    case 'target_date':
      return TARGET_DATE_REQUIRED_MESSAGE
    case 'industry_other':
      return INDUSTRY_OTHER_REQUIRED_MESSAGE
    case 'target_audience_other':
      return TARGET_AUDIENCE_OTHER_REQUIRED_MESSAGE
    case 'project_summary':
      return PROJECT_SUMMARY_LENGTH_MESSAGE
    case 'transcript':
      if (msg.includes('80') || msg.includes('at least')) {
        return 'Transcript must be at least 80 characters after trim.'
      }
      if (msg.includes('24') || msg.includes('at most')) {
        return 'Transcript must be at most 24,000 characters.'
      }
      return GENERIC_FIELD_MESSAGE
    case 'project_description':
      return PROJECT_DESCRIPTION_LENGTH_MESSAGE
    case 'project_name':
      return PROJECT_NAME_MAX_MESSAGE
    case 'hosting_notes':
      return HOSTING_NOTES_MAX_MESSAGE
    case 'out_of_scope':
      if (msg.includes('5') || msg.includes('most')) {
        return OUT_OF_SCOPE_COUNT_MESSAGE
      }
      return OUT_OF_SCOPE_LINE_MAX_MESSAGE
    case 'external_dependencies':
      if (msg.includes('3') || msg.includes('most')) {
        return EXTERNAL_DEP_COUNT_MESSAGE
      }
      return EXTERNAL_DEP_LINE_MAX_MESSAGE
    case 'integration_categories':
      return INTEGRATION_NONE_EXCLUSIVE_MESSAGE
    case 'attachments':
      if (msg.includes('total') || msg.includes('bytes')) {
        return ATTACHMENTS_TOTAL_SIZE_MESSAGE
      }
      if (msg.includes('at most') || msg.includes('3')) {
        return ATTACHMENTS_COUNT_MESSAGE
      }
      return ATTACHMENT_ITEM_MESSAGE
    case 'preprocessing':
      return PREPROCESSING_INVALID_MESSAGE
    default:
      if (
        backendField === 'project_type' ||
        backendField === 'target_audience' ||
        backendField === 'delivery_urgency' ||
        backendField === 'data_sensitivity' ||
        backendField === 'detail_level' ||
        backendField === 'output_format' ||
        backendField === 'industry' ||
        backendField === 'delivery_approach' ||
        backendField === 'team_context' ||
        backendField === 'risk_level'
      ) {
        return SELECT_REQUIRED_MESSAGE
      }
      return GENERIC_FIELD_MESSAGE
  }
}

function mergeDetailItems(detail: unknown): Array<{ loc: unknown[]; msg: string }> {
  if (!Array.isArray(detail)) {
    return []
  }
  const out: Array<{ loc: unknown[]; msg: string }> = []
  for (const item of detail) {
    if (item && typeof item === 'object' && 'loc' in item) {
      const loc = (item as { loc?: unknown }).loc
      const msg = String((item as { msg?: unknown }).msg ?? '')
      if (Array.isArray(loc)) {
        out.push({ loc, msg })
      }
    }
  }
  return out
}

/**
 * Parse failed `POST /api/v2/estimate` responses into either field-level validation errors
 * or a single safe generic message (no raw HTTP bodies for 422).
 */
export function parseStructuredEstimateFailure(status: number, bodyText: string): ParsedEstimateFailure {
  const trimmed = bodyText.trim()
  if (status !== 422) {
    if (!trimmed) {
      return { kind: 'generic', message: 'The request could not be completed. Please try again.' }
    }
    return { kind: 'generic', message: 'The request could not be completed. Please try again.' }
  }

  let detail: unknown
  try {
    detail = trimmed ? (JSON.parse(trimmed) as { detail?: unknown }).detail : undefined
  } catch {
    return {
      kind: 'generic',
      message: 'We could not validate the form. Please check your input and try again.',
    }
  }

  const items = mergeDetailItems(detail)
  if (items.length === 0) {
    return {
      kind: 'generic',
      message: 'We could not validate the form. Please check your input and try again.',
    }
  }

  const fieldErrors: Record<string, string> = {}
  for (const { loc, msg } of items) {
    let backend = firstMappedBackendField(loc)
    if (!backend) {
      backend = inferBackendFieldFromMessage(msg)
    }
    if (!backend) {
      continue
    }
    const uiKey = uiKeyForBackendField(backend)
    const human = humanMessageForBackendField(backend, msg)
    if (!fieldErrors[uiKey]) {
      fieldErrors[uiKey] = human
    }
  }

  if (Object.keys(fieldErrors).length > 0) {
    return {
      kind: 'validation',
      fieldErrors,
      formSummary: VALIDATION_SUMMARY_BANNER,
    }
  }

  return {
    kind: 'generic',
    message: 'We could not validate the form. Please check your input and try again.',
  }
}

function humanizeSingleZodIssue(issue: ZodIssue): string {
  const key = issue.path.length > 0 ? String(issue.path[0]) : '_form'
  const msg = issue.message.trim()
  if (/^[a-z][a-z0-9_]* is required$/i.test(msg)) {
    return SELECT_REQUIRED_MESSAGE
  }

  if (key === 'integrationCustomText') {
    return issue.message
  }
  if (key === 'deliverablesText') {
    return issue.message
  }
  if (key === 'targetDate') {
    return issue.message
  }
  if (key === 'targetAudienceOther') {
    return issue.message
  }
  if (key === 'industryOther') {
    return issue.message
  }
  if (key === 'projectSummary') {
    if (issue.code === 'too_small' || issue.code === 'too_big') {
      return PROJECT_SUMMARY_LENGTH_MESSAGE
    }
  }
  if (key === 'transcript') {
    return issue.message
  }
  if (key === 'projectDescription') {
    if (issue.code === 'too_small' || issue.code === 'too_big') {
      return PROJECT_DESCRIPTION_LENGTH_MESSAGE
    }
  }
  if (key === 'projectName' && issue.code === 'too_big') {
    return PROJECT_NAME_MAX_MESSAGE
  }
  if (
    key === 'projectType' ||
    key === 'targetAudience' ||
    key === 'deliveryUrgency' ||
    key === 'dataSensitivity' ||
    key === 'detailLevel' ||
    key === 'outputFormat'
  ) {
    if (msg.toLowerCase().includes('invalid')) {
      return SELECT_INVALID_MESSAGE
    }
    return SELECT_REQUIRED_MESSAGE
  }
  if (key === 'industry' || key === 'deliveryApproach' || key === 'teamContext' || key === 'riskLevel') {
    if (msg.toLowerCase().includes('invalid')) {
      return SELECT_INVALID_MESSAGE
    }
    return SELECT_REQUIRED_MESSAGE
  }
  if (key === 'preprocessing') {
    return PREPROCESSING_INVALID_MESSAGE
  }
  if (key === 'attachments') {
    return ATTACHMENTS_COUNT_MESSAGE
  }
  if (key === 'uiLanguages') {
    return 'Please select at most 3 UI languages.'
  }

  if (issue.path.length === 0 || key === '_form') {
    return 'Please review the form.'
  }

  return GENERIC_FIELD_MESSAGE
}

/** Map Zod issues from `parseEstimationForm` to human-readable English field messages (UI keys). */
export function humanizeZodIssuesToFieldErrors(issues: readonly ZodIssue[]): Record<string, string> {
  const map: Record<string, string> = {}
  for (const issue of issues) {
    const fieldKey = issue.path.length > 0 ? String(issue.path[0]) : '_form'
    if (!map[fieldKey]) {
      map[fieldKey] = humanizeSingleZodIssue(issue)
    }
  }
  return map
}
