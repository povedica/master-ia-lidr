export const PROJECT_TYPES = [
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

export const TARGET_AUDIENCES = [
  'b2c_consumers',
  'b2b_smb',
  'b2b_enterprise',
  'internal_employees',
  'mixed',
  'other',
] as const

export const INDUSTRIES = [
  '',
  'fintech',
  'health',
  'ecommerce',
  'education',
  'public_sector',
  'industrial',
  'generic_b2b',
  'other',
] as const

export const REQUIRED_SELECT_PLACEHOLDER = '— Select —'

export const TRANSCRIPT_MIN = 80
export const TRANSCRIPT_MAX = 24_000

export function humanizeEnum(value: string): string {
  return value.replace(/_/g, ' ')
}
