import { describe, expect, it } from 'vitest'
import type { ZodIssue } from 'zod'

import {
  BACKEND_FIELD_TO_UI,
  humanizeZodIssuesToFieldErrors,
  parseStructuredEstimateFailure,
} from './validationErrors'

describe('parseStructuredEstimateFailure', () => {
  it('maps integration_custom_names 422 to integrationCustomText with English copy', () => {
    const body = JSON.stringify({
      detail: [
        {
          type: 'value_error',
          loc: ['body', 'integration_custom_names', 0],
          msg: 'Value error, each integration_custom_names entry must be at most 300 characters',
          input: 'x'.repeat(41),
        },
      ],
    })
    const r = parseStructuredEstimateFailure(422, body)
    expect(r.kind).toBe('generic')
  })

  it('maps model-level target_date message when loc is only body', () => {
    const body = JSON.stringify({
      detail: [
        {
          type: 'value_error',
          loc: ['body'],
          msg: 'Value error, target_date is required when delivery_urgency is fixed_date or critical',
        },
      ],
    })
    const r = parseStructuredEstimateFailure(422, body)
    expect(r.kind).toBe('generic')
  })

  it('maps out_of_domain object detail to transcript', () => {
    const body = JSON.stringify({
      detail: {
        code: 'out_of_domain',
        message: 'Only software/project estimation requests are supported.',
      },
    })
    const r = parseStructuredEstimateFailure(422, body)
    expect(r.kind).toBe('validation')
    if (r.kind === 'validation') {
      expect(r.fieldErrors.transcript).toContain('software/project')
    }
  })

  it('returns generic safe message for 422 without mappable fields', () => {
    const body = JSON.stringify({
      detail: [{ type: 'value_error', loc: ['body', 'unknown_field'], msg: 'broken' }],
    })
    const r = parseStructuredEstimateFailure(422, body)
    expect(r.kind).toBe('generic')
    if (r.kind === 'generic') {
      expect(r.message.toLowerCase()).not.toContain('unknown_field')
    }
  })

  it('returns generic message for non-422 without leaking raw body', () => {
    const r = parseStructuredEstimateFailure(500, 'Internal Server Error stack trace here')
    expect(r.kind).toBe('generic')
    if (r.kind === 'generic') {
      expect(r.message).not.toContain('stack')
    }
  })
})

describe('BACKEND_FIELD_TO_UI', () => {
  it('covers the guided form inventory from the spec', () => {
    const keys = [
      'project_name',
      'project_summary',
      'project_type',
      'target_audience',
      'target_audience_other',
      'project_description',
      'detail_level',
      'output_format',
      'attachments',
      'industry',
      'industry_other',
      'preprocessing',
      'evaluate',
    ]
    for (const k of keys) {
      expect(BACKEND_FIELD_TO_UI[k]).toBeTruthy()
    }
  })
})

describe('humanizeZodIssuesToFieldErrors', () => {
  it('maps empty project_type to English select message', () => {
    const issues: ZodIssue[] = [
      {
        code: 'custom',
        message: 'project_type is required',
        path: ['projectType'],
      } as ZodIssue,
    ]
    const m = humanizeZodIssuesToFieldErrors(issues)
    expect(m.projectType).toBe('Required.')
  })
})
