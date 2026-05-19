import { parseStructuredEstimateFailure, type ParsedEstimateFailure } from './validationErrors'

/** Maps session estimate 422 responses to simplified form field keys. */
const SESSION_BACKEND_TO_UI: Record<string, string> = {
  project_name: 'projectName',
  one_line_summary: 'oneLineSummary',
  project_type: 'projectType',
  transcript: 'transcript',
  target_audience: 'targetAudience',
  industry: 'industry',
  additional_extra_info: 'additionalExtraInfo',
  attachments: 'attachments',
}

export function parseSessionEstimateFailure(status: number, bodyText: string): ParsedEstimateFailure {
  const parsed = parseStructuredEstimateFailure(status, bodyText)
  if (parsed.kind !== 'validation') {
    return parsed
  }
  const remapped: Record<string, string> = {}
  for (const [key, message] of Object.entries(parsed.fieldErrors)) {
    const uiKey = SESSION_BACKEND_TO_UI[key] ?? key
    remapped[uiKey] = message
  }
  return { ...parsed, fieldErrors: remapped }
}
