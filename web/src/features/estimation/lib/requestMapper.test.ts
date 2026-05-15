import { describe, expect, it } from 'vitest'

import {
  estimationFormSchema,
  findInvalidCustomIntegrationLines,
  mapEstimationFormToRequestBody,
  parseEstimationForm,
} from './requestMapper'

/** Valid raw payload except `projectType` left empty (unselected required `<select>`). */
function validRawExceptProjectType(projectType: string) {
  return {
    projectName: '',
    projectSummary: 'x'.repeat(20),
    projectType,
    targetAudience: 'b2b_enterprise',
    targetAudienceOther: '',
    industry: '',
    industryOther: '',
    projectDescription: 'y'.repeat(100),
    deliverablesText: 'A\nB\nC',
    outOfScopeText: '',
    deliveryUrgency: 'standard',
    targetDate: '',
    deliveryApproach: '',
    integrationCategories: [],
    integrationCustomText: '',
    dataSensitivity: 'internal_business',
    hostingConstraints: [],
    hostingNotes: '',
    teamContext: '',
    uiLanguages: [],
    riskLevel: '',
    externalDependenciesText: '',
    detailLevel: 'medium',
    outputFormat: 'phases_table',
    attachments: [],
    preprocessing: 'none',
    evaluate: true,
  }
}

describe('mapEstimationFormToRequestBody', () => {
  it('maps minimal valid guided form to API JSON shape', () => {
    const body = mapEstimationFormToRequestBody(
      parseEstimationForm({
        projectName: '',
        projectSummary:
          'B2B partner portal for support intake, SLA tracking, and quarterly reporting.',
        projectType: 'web_saas',
        targetAudience: 'b2b_enterprise',
        targetAudienceOther: '',
        industry: '',
        industryOther: '',
        projectDescription: 'x'.repeat(100),
        deliverablesText: 'A\nB\nC',
        outOfScopeText: '',
        deliveryUrgency: 'standard',
        targetDate: '',
        deliveryApproach: '',
        integrationCategories: [],
        integrationCustomText: '',
        dataSensitivity: 'internal_business',
        hostingConstraints: [],
        hostingNotes: '',
        teamContext: '',
        uiLanguages: [],
        riskLevel: '',
        externalDependenciesText: '',
        detailLevel: 'medium',
        outputFormat: 'phases_table',
        attachments: [],
        preprocessing: 'none',
        evaluate: true,
      }),
    )
    expect(body.project_type).toBe('web_saas')
    expect(body.deliverables).toEqual(['A', 'B', 'C'])
    expect(body.project_name).toBeNull()
    expect(body.industry).toBeNull()
    expect(body.preprocessing).toBe('none')
    expect(body.evaluate).toBe(true)
  })

  it('maps list optional fields and trims strings', () => {
    const body = mapEstimationFormToRequestBody(
      parseEstimationForm({
        projectName: '  My Project  ',
        projectSummary:
          'B2B partner portal for support intake, SLA tracking, and quarterly reporting.',
        projectType: 'api_platform',
        targetAudience: 'b2b_smb',
        targetAudienceOther: '',
        industry: 'fintech',
        industryOther: '',
        projectDescription: 'y'.repeat(100),
        deliverablesText: ' one \n two \n three ',
        outOfScopeText: ' out1 \n out2 ',
        deliveryUrgency: 'flexible',
        targetDate: '',
        deliveryApproach: 'mvp_then_iterate',
        integrationCategories: ['payments', 'crm'],
        integrationCustomText: 'Custom A\nCustom B',
        dataSensitivity: 'pii_light',
        hostingConstraints: ['cloud_managed'],
        hostingNotes: ' notes ',
        teamContext: 'vendor_led',
        uiLanguages: ['en', 'es'],
        riskLevel: 'medium',
        externalDependenciesText: 'Dep A\nDep B',
        detailLevel: 'summary',
        outputFormat: 'narrative',
        attachments: [
          {
            filename: 'a.txt',
            content_type: 'text/plain',
            content_base64: 'QUJDCg==',
          },
        ],
        preprocessing: 'inline_cleaning',
        evaluate: false,
      }),
    )
    expect(body.project_name).toBe('My Project')
    expect(body.out_of_scope).toEqual(['out1', 'out2'])
    expect(body.integration_categories).toEqual(['payments', 'crm'])
    expect(body.integration_custom_names).toEqual(['Custom A', 'Custom B'])
    expect(body.hosting_constraints).toEqual(['cloud_managed'])
    expect(body.hosting_notes).toBe('notes')
    expect(body.team_context).toBe('vendor_led')
    expect(body.ui_languages).toEqual(['en', 'es'])
    expect(body.risk_level).toBe('medium')
    expect(body.external_dependencies).toEqual(['Dep A', 'Dep B'])
    expect(body.attachments).toHaveLength(1)
    expect(body.evaluate).toBe(false)
  })

  it('includes target_date when urgency requires it', () => {
    const body = mapEstimationFormToRequestBody(
      parseEstimationForm({
        projectName: '',
        projectSummary:
          'B2B partner portal for support intake, SLA tracking, and quarterly reporting.',
        projectType: 'web_saas',
        targetAudience: 'b2b_enterprise',
        targetAudienceOther: '',
        industry: '',
        industryOther: '',
        projectDescription: 'z'.repeat(100),
        deliverablesText: 'a\nb\nc',
        outOfScopeText: '',
        deliveryUrgency: 'fixed_date',
        targetDate: '2030-01-15',
        deliveryApproach: '',
        integrationCategories: [],
        integrationCustomText: '',
        dataSensitivity: 'internal_business',
        hostingConstraints: [],
        hostingNotes: '',
        teamContext: '',
        uiLanguages: [],
        riskLevel: '',
        externalDependenciesText: '',
        detailLevel: 'medium',
        outputFormat: 'phases_table',
        attachments: [],
        preprocessing: 'none',
        evaluate: true,
      }),
    )
    expect(body.target_date).toBe('2030-01-15')
  })
})

describe('estimationFormSchema', () => {
  it('rejects empty required select (project_type)', () => {
    const result = estimationFormSchema.safeParse(validRawExceptProjectType(''))
    expect(result.success).toBe(false)
    if (!result.success) {
      const messages = result.error.issues.map((i) => i.message)
      expect(messages.some((m) => m.includes('project_type'))).toBe(true)
    }
  })

  it('accepts valid project_type after selection', () => {
    const result = estimationFormSchema.safeParse(validRawExceptProjectType('web_saas'))
    expect(result.success).toBe(true)
  })

  it('accepts empty preprocessing (optional) and maps to none in API body', () => {
    const parsed = parseEstimationForm({
      ...validRawExceptProjectType('web_saas'),
      preprocessing: '',
    })
    expect(parsed.preprocessing).toBe('')
    const body = mapEstimationFormToRequestBody(parsed)
    expect(body.preprocessing).toBe('none')
  })

  it('rejects custom integration lines longer than 40 characters', () => {
    const result = estimationFormSchema.safeParse({
      ...validRawExceptProjectType('web_saas'),
      integrationCustomText: `Valid integration\n${'x'.repeat(41)}`,
    })

    expect(result.success).toBe(false)
    if (!result.success) {
      expect(result.error.issues).toEqual(
        expect.arrayContaining([
          expect.objectContaining({
            path: ['integrationCustomText'],
            message: 'Cada integración debe ocupar una línea y tener como máximo 40 caracteres.',
          }),
        ]),
      )
    }
  })

  it('reports invalid custom integration line numbers', () => {
    expect(
      findInvalidCustomIntegrationLines(`  ${'x'.repeat(41)}  \n\nValid\n${'y'.repeat(42)}`),
    ).toEqual([1, 4])
  })
})
