import { describe, expect, it } from 'vitest'

import {
  buildInitialSimplifiedForm,
  mapToSessionEstimateBody,
  parseSimplifiedForm,
  payloadToSimplifiedForm,
  simplifiedFormSchema,
} from './simplifiedForm'
import { humanizeZodIssuesToFieldErrors } from './validationErrors'

const validTranscript = 'x'.repeat(80)

describe('mapToSessionEstimateBody', () => {
  it('maps simplified fields to snake_case API body', () => {
    const body = mapToSessionEstimateBody(
      parseSimplifiedForm({
        projectName: 'NeoBank',
        oneLineSummary: 'Digital banking',
        projectType: 'mobile_app',
        transcript: validTranscript,
        targetAudience: 'b2c_consumers',
        targetAudienceOther: '',
        industry: 'fintech',
        additionalExtraInfo: 'Notes',
        attachments: [
          {
            file_id: 'f1',
            name: 'notes.txt',
            mime_type: 'text/plain',
            content_base64: 'QUJDCg==',
          },
        ],
      }),
    )
    expect(body.project_name).toBe('NeoBank')
    expect(body.one_line_summary).toBe('Digital banking')
    expect(body.project_type).toBe('mobile_app')
    expect(body.transcript).toBe(validTranscript)
    expect(body.target_audience).toBe('b2c_consumers')
    expect(body.industry).toBe('fintech')
    expect(body.additional_extra_info).toBe('Notes')
    expect(body.attachments).toHaveLength(1)
    expect(body).not.toHaveProperty('deliverables')
    expect(body).not.toHaveProperty('project_description')
  })

  it('omits optional strings as null', () => {
    const body = mapToSessionEstimateBody(
      parseSimplifiedForm({
        ...buildInitialSimplifiedForm(),
        projectName: 'P',
        projectType: 'web_saas',
        transcript: validTranscript,
        targetAudience: 'b2b_enterprise',
      }),
    )
    expect(body.one_line_summary).toBeNull()
    expect(body.industry).toBeNull()
    expect(body.additional_extra_info).toBeNull()
    expect(body.attachments).toEqual([])
  })
})

describe('payloadToSimplifiedForm', () => {
  it('restores camelCase fields from session input_payload', () => {
    const form = payloadToSimplifiedForm({
      project_name: 'NeoBank',
      one_line_summary: 'Banking',
      project_type: 'mobile_app',
      transcript: validTranscript,
      target_audience: 'b2c_consumers',
      industry: 'fintech',
      additional_extra_info: 'Extra',
    })
    expect(form.projectName).toBe('NeoBank')
    expect(form.oneLineSummary).toBe('Banking')
    expect(form.projectType).toBe('mobile_app')
    expect(form.transcript).toBe(validTranscript)
    expect(form.attachments).toEqual([])
  })

  it('restores attachments from session input_payload', () => {
    const form = payloadToSimplifiedForm({
      project_name: 'NeoBank',
      project_type: 'mobile_app',
      transcript: validTranscript,
      target_audience: 'b2c_consumers',
      attachments: [
        {
          file_id: 'f1',
          name: 'notes.txt',
          mime_type: 'text/plain',
          content_base64: 'QUJDCg==',
        },
      ],
    })
    expect(form.attachments).toHaveLength(1)
    expect(form.attachments[0]?.name).toBe('notes.txt')
  })
})

describe('simplifiedFormSchema', () => {
  it('rejects empty project_name and short transcript', () => {
    const result = simplifiedFormSchema.safeParse({
      ...buildInitialSimplifiedForm(),
      projectName: '',
      projectType: 'web_saas',
      transcript: 'short',
      targetAudience: 'b2b_enterprise',
    })
    expect(result.success).toBe(false)
    if (!result.success) {
      const human = humanizeZodIssuesToFieldErrors(result.error.issues)
      expect(human.projectName).toBeTruthy()
      expect(human.transcript).toContain('80')
    }
  })

  it('accepts valid minimal form', () => {
    const result = simplifiedFormSchema.safeParse({
      ...buildInitialSimplifiedForm(),
      projectName: 'App',
      projectType: 'web_saas',
      transcript: validTranscript,
      targetAudience: 'b2b_enterprise',
    })
    expect(result.success).toBe(true)
  })
})
