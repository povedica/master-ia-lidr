import {
  cloneElement,
  type FormEvent,
  type ReactElement,
  useEffect,
  useMemo,
  useState,
  useRef,
} from 'react'
import ReactMarkdown from 'react-markdown'
import { ZodError } from 'zod'

import { useEstimateStream } from '../hooks/useEstimateStream'
import { estimateStructuredUrl } from '../api/estimateApi'
import { filesToAttachments } from '../lib/fileToBase64'
import {
  estimationFormSchema,
  mapEstimationFormToRequestBody,
  parseEstimationForm,
  type EstimationFormValues,
} from '../lib/requestMapper'
import { humanizeZodIssuesToFieldErrors } from '../lib/validationErrors'

const REQUIRED_SELECT_PLACEHOLDER = '— Select —'

function buildInitialForm(): EstimationFormValues {
  return {
    projectName: '',
    projectSummary: '',
    projectType: '',
    targetAudience: '',
    targetAudienceOther: '',
    industry: '',
    industryOther: '',
    projectDescription: '',
    deliverablesText: '',
    outOfScopeText: '',
    deliveryUrgency: '',
    targetDate: '',
    deliveryApproach: '',
    integrationCategories: [],
    integrationCustomText: '',
    dataSensitivity: '',
    hostingConstraints: [],
    hostingNotes: '',
    teamContext: '',
    uiLanguages: [],
    riskLevel: '',
    externalDependenciesText: '',
    detailLevel: '',
    outputFormat: '',
    attachments: [],
    preprocessing: '',
    evaluate: false,
  }
}

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

const TARGET_AUDIENCES = [
  'b2c_consumers',
  'b2b_smb',
  'b2b_enterprise',
  'internal_employees',
  'mixed',
  'other',
] as const

const INDUSTRIES = [
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

const DELIVERY_URGENCY = ['flexible', 'standard', 'fixed_date', 'critical'] as const

const DELIVERY_APPROACH = ['', 'mvp_then_iterate', 'single_release', 'phased_roadmap', 'unknown'] as const

const INTEGRATION_ALL = [
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

const HOSTING_ALL = [
  'no_preference',
  'cloud_managed',
  'customer_cloud_only',
  'on_prem',
  'air_gapped',
  'hybrid',
] as const

const TEAM_CONTEXT = ['', 'client_only', 'vendor_led', 'mixed_team', 'unknown'] as const

const UI_LANG = ['en', 'es', 'pt', 'fr', 'de', 'other'] as const

const RISK = ['', 'low', 'medium', 'high', 'unknown'] as const

const DATA_SENS = [
  'public_only',
  'internal_business',
  'pii_light',
  'pii_heavy',
  'regulated_unknown',
] as const

const DETAIL = ['summary', 'medium', 'detailed'] as const

const OUTPUT = ['phases_table', 'line_items', 'narrative'] as const

const PREPROCESSING = ['none', 'inline_cleaning', 'two_phase'] as const

/** DOM order for scrolling to the first invalid field (top → bottom). */
const FORM_FIELD_ORDER: readonly string[] = [
  'projectName',
  'projectSummary',
  'projectType',
  'targetAudience',
  'targetAudienceOther',
  'projectDescription',
  'deliverablesText',
  'deliveryUrgency',
  'targetDate',
  'dataSensitivity',
  'detailLevel',
  'outputFormat',
  'attachments',
  'outOfScopeText',
  'deliveryApproach',
  'integrationCategories',
  'integrationCustomText',
  'industry',
  'industryOther',
  'hostingConstraints',
  'hostingNotes',
  'teamContext',
  'uiLanguages',
  'riskLevel',
  'externalDependenciesText',
  'preprocessing',
]

const DETAILS_FIELD_KEYS = new Set<string>([
  'outOfScopeText',
  'deliveryApproach',
  'integrationCategories',
  'integrationCustomText',
  'industry',
  'industryOther',
  'hostingConstraints',
  'hostingNotes',
  'teamContext',
  'uiLanguages',
  'riskLevel',
  'externalDependenciesText',
  'preprocessing',
])

const CONTROL_ERR_RING =
  'ring-2 ring-red-500/45 ring-offset-2 ring-offset-white dark:ring-offset-slate-950'

type StructuredWorkRow = {
  key: string
  phaseLabel: string | null
  name: string
  hours: number
  cost_eur: number
}

function collectStructuredWorkRows(data: Record<string, unknown>): StructuredWorkRow[] {
  const rows: StructuredWorkRow[] = []
  let seq = 0
  const phasesRaw = Array.isArray(data.phases) ? (data.phases as Record<string, unknown>[]) : []
  for (const ph of phasesRaw) {
    const phaseName = typeof ph.name === 'string' ? ph.name.trim() : ''
    const items = Array.isArray(ph.items) ? (ph.items as Record<string, unknown>[]) : []
    for (const it of items) {
      rows.push({
        key: `p-${seq++}`,
        phaseLabel: phaseName.length > 0 ? phaseName : null,
        name: String(it.name ?? ''),
        hours: typeof it.hours === 'number' ? it.hours : 0,
        cost_eur: typeof it.cost_eur === 'number' ? it.cost_eur : 0,
      })
    }
  }
  const lineItemsRaw = Array.isArray(data.line_items)
    ? (data.line_items as Record<string, unknown>[])
    : []
  for (const it of lineItemsRaw) {
    rows.push({
      key: `l-${seq++}`,
      phaseLabel: null,
      name: String(it.name ?? ''),
      hours: typeof it.hours === 'number' ? it.hours : 0,
      cost_eur: typeof it.cost_eur === 'number' ? it.cost_eur : 0,
    })
  }
  return rows
}

function StructuredEstimateSummary({ data }: { data: Record<string, unknown> }) {
  const title = typeof data.title === 'string' ? data.title : '—'
  const summary = typeof data.summary === 'string' ? data.summary : ''
  const totals = data.totals as Record<string, unknown> | undefined
  const hours = totals && typeof totals.hours === 'number' ? totals.hours : null
  const cost = totals && typeof totals.cost_eur === 'number' ? totals.cost_eur : null
  const duration =
    typeof data.duration_weeks === 'number' ? data.duration_weeks.toFixed(1) : '—'
  const confidence =
    typeof data.confidence === 'number' ? (data.confidence * 100).toFixed(0) + '%' : '—'

  const workRows = collectStructuredWorkRows(data)
  const showPhaseColumn = workRows.some((r) => r.phaseLabel !== null)

  const metricCards: { label: string; value: string }[] = [
    { label: 'Total hours', value: hours !== null ? String(hours) : '—' },
    { label: 'Total EUR', value: cost !== null ? cost.toLocaleString() : '—' },
    { label: 'Duration (weeks)', value: duration },
    { label: 'Confidence', value: confidence },
  ]

  return (
    <div className="mt-5 rounded-xl border border-slate-200 bg-slate-50 p-6 sm:p-8 dark:border-slate-700 dark:bg-slate-900/35">
      <div className="space-y-8">
        <div>
          <h3 className="text-lg font-semibold tracking-tight text-slate-900 dark:text-white">{title}</h3>
          {summary ? (
            <p className="mt-3 max-w-prose text-sm leading-relaxed text-slate-600 dark:text-slate-300">{summary}</p>
          ) : null}
        </div>
        <dl className="grid grid-cols-2 gap-4 sm:grid-cols-4">
          {metricCards.map(({ label, value }) => (
            <div
              key={label}
              className="rounded-md border border-slate-200 bg-white p-4 dark:border-slate-600 dark:bg-slate-950"
            >
              <dt className="text-[11px] font-medium uppercase tracking-wider text-slate-500 dark:text-slate-400">
                {label}
              </dt>
              <dd className="mt-2 text-2xl font-bold tabular-nums tracking-tight text-slate-900 dark:text-white">
                {value}
              </dd>
            </div>
          ))}
        </dl>
        {workRows.length > 0 ? (
          <div>
            <h4 className="mb-3 text-sm font-semibold text-slate-900 dark:text-white">Work items</h4>
            <p className="mb-3 text-xs text-slate-500 dark:text-slate-400">
              Rows include tasks inside <code className="text-xs">phases</code> and any top-level{' '}
              <code className="text-xs">line_items</code>; totals match the sum of all rows shown.
            </p>
            <div className="overflow-x-auto rounded-md border border-slate-200 bg-white dark:border-slate-600 dark:bg-slate-950">
              <table className="min-w-full border-collapse text-left text-xs">
                <thead className="bg-slate-100 dark:bg-slate-900">
                  <tr>
                    {showPhaseColumn ? (
                      <th className="border-b border-slate-200 px-3 py-2 font-medium text-slate-600 dark:border-slate-700 dark:text-slate-300">
                        Phase
                      </th>
                    ) : null}
                    <th className="border-b border-slate-200 px-3 py-2 font-medium text-slate-600 dark:border-slate-700 dark:text-slate-300">
                      Name
                    </th>
                    <th className="border-b border-slate-200 px-3 py-2 font-medium text-slate-600 dark:border-slate-700 dark:text-slate-300">
                      Hours
                    </th>
                    <th className="border-b border-slate-200 px-3 py-2 font-medium text-slate-600 dark:border-slate-700 dark:text-slate-300">
                      EUR
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {workRows.map((row) => (
                    <tr
                      key={row.key}
                      className="odd:bg-white even:bg-slate-50 dark:odd:bg-slate-950 dark:even:bg-slate-900/50"
                    >
                      {showPhaseColumn ? (
                        <td className="border-b border-slate-100 px-3 py-2 text-slate-600 dark:border-slate-800 dark:text-slate-300">
                          {row.phaseLabel ?? (row.key.startsWith('l-') ? 'Other' : '—')}
                        </td>
                      ) : null}
                      <td className="border-b border-slate-100 px-3 py-2 text-slate-800 dark:border-slate-800 dark:text-slate-200">
                        {row.name}
                      </td>
                      <td className="border-b border-slate-100 px-3 py-2 tabular-nums text-slate-800 dark:border-slate-800 dark:text-slate-200">
                        {row.hours}
                      </td>
                      <td className="border-b border-slate-100 px-3 py-2 tabular-nums text-slate-800 dark:border-slate-800 dark:text-slate-200">
                        {row.cost_eur}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        ) : null}
      </div>
    </div>
  )
}

function firstOrderedFieldWithError(
  fieldErrors: Record<string, string>,
  order: readonly string[],
): string | null {
  for (const k of order) {
    if (fieldErrors[k]) {
      return k
    }
  }
  const rest = Object.keys(fieldErrors).filter((k) => k !== '_form')
  return rest[0] ?? null
}

export function EstimationWorkbench() {
  const { markdown, structuredResult, loading, error, doneMeta, run, cancel } = useEstimateStream()
  const [form, setForm] = useState<EstimationFormValues>(buildInitialForm)
  const [clientError, setClientError] = useState<string | null>(null)
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({})
  const [moreDetailsOpen, setMoreDetailsOpen] = useState(false)
  const [fileList, setFileList] = useState<File[]>([])
  const hadFieldErrorsRef = useRef(false)

  useEffect(() => {
    const empty = Object.keys(fieldErrors).length === 0
    if (empty) {
      hadFieldErrorsRef.current = false
      return
    }
    if (hadFieldErrorsRef.current) {
      return
    }
    hadFieldErrorsRef.current = true

    const first = firstOrderedFieldWithError(fieldErrors, FORM_FIELD_ORDER)
    if (!first) {
      return
    }
    if (DETAILS_FIELD_KEYS.has(first)) {
      setMoreDetailsOpen(true)
    }
    const t = window.setTimeout(() => {
      const el = document.getElementById(first)
      el?.scrollIntoView({ behavior: 'smooth', block: 'center' })
      if (el instanceof HTMLElement && typeof el.focus === 'function') {
        el.focus()
      }
    }, 100)
    return () => window.clearTimeout(t)
  }, [fieldErrors])

  useEffect(() => {
    setFieldErrors((prev) => {
      const keysWithErrors = Object.keys(prev).filter((k) => k !== '_form')
      if (keysWithErrors.length === 0) {
        return prev
      }
      const raw = { ...form, attachments: form.attachments }
      const result = estimationFormSchema.safeParse(raw)
      const fromZod = result.success
        ? ({} as Record<string, string>)
        : humanizeZodIssuesToFieldErrors(result.error.issues)

      const next: Record<string, string> = { ...prev }
      let changed = false

      for (const k of keysWithErrors) {
        if (k === 'attachments') {
          continue
        }
        if (!fromZod[k]) {
          delete next[k]
          changed = true
        } else if (fromZod[k] !== prev[k]) {
          next[k] = fromZod[k]
          changed = true
        }
      }
      for (const [k, v] of Object.entries(fromZod)) {
        if (next[k] !== v) {
          next[k] = v
          changed = true
        }
      }
      if (!changed) {
        return prev
      }
      if (prev._form && !next._form) {
        next._form = prev._form
      }
      return next
    })
  }, [form])

  const needsTargetDate = useMemo(
    () => form.deliveryUrgency === 'fixed_date' || form.deliveryUrgency === 'critical',
    [form.deliveryUrgency],
  )

  async function onSubmit(ev: FormEvent) {
    ev.preventDefault()
    setClientError(null)
    setFieldErrors({})
    let attachments = form.attachments
    try {
      if (fileList.length > 0) {
        attachments = await filesToAttachments(fileList)
      }
    } catch (exc) {
      setFieldErrors((prev) => ({
        ...prev,
        attachments: exc instanceof Error ? exc.message : 'Invalid attachments.',
      }))
      return
    }

    const raw = { ...form, attachments }
    try {
      const parsed = parseEstimationForm(raw)
      const body = mapEstimationFormToRequestBody(parsed)
      const outcome = await run(body)
      if (outcome && !outcome.ok) {
        if (outcome.kind === 'validation') {
          setFieldErrors(outcome.fieldErrors)
          setClientError(outcome.formSummary ?? null)
          return
        }
        return
      }
    } catch (exc) {
      if (exc instanceof ZodError) {
        setFieldErrors(humanizeZodIssuesToFieldErrors(exc.issues))
        return
      }
      setClientError(exc instanceof Error ? exc.message : 'We could not validate the form.')
    }
  }

  return (
    <div className="mx-auto max-w-3xl px-4 py-8 text-left text-slate-900 dark:text-slate-100">
      <header className="mb-8 border-b border-slate-200 pb-6 dark:border-slate-800">
        <h1 className="text-2xl font-semibold text-slate-900 dark:text-white">Estimador CAG</h1>
        <p className="mt-2 text-sm text-slate-600 dark:text-slate-400">
          Guided estimation form. Structured output from{' '}
          <code className="rounded bg-slate-200 px-1 py-0.5 text-xs text-slate-800 dark:bg-slate-800 dark:text-slate-100">
            {estimateStructuredUrl()}
          </code>{' '}
          (<code className="text-xs">POST /api/v2/estimate</code>, JSON <code className="text-xs">result</code>).
        </p>
      </header>

      {error ? (
        <div
          role="alert"
          className="sticky top-2 z-20 mb-6 rounded-lg border border-red-300/90 bg-red-50/95 p-4 text-sm text-red-900 shadow-lg backdrop-blur-sm dark:border-red-800/80 dark:bg-red-950/95 dark:text-red-100"
        >
          <p className="font-semibold text-red-950 dark:text-red-50">Request failed</p>
          <p className="mt-2 max-h-40 overflow-y-auto whitespace-pre-wrap font-mono text-xs leading-relaxed text-red-900/90 dark:text-red-100/90">
            {error}
          </p>
        </div>
      ) : null}

      <form
        onSubmit={onSubmit}
        className="space-y-6"
      >
        <Field name="projectName" label="Project name (optional)" error={fieldErrors.projectName}>
          <input
            className="w-full rounded border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 focus:outline-none focus-visible:border-violet-500 focus-visible:ring-2 focus-visible:ring-violet-500 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100"
            maxLength={120}
            value={form.projectName}
            onChange={(e) => setForm((f) => ({ ...f, projectName: e.target.value }))}
          />
        </Field>

        <Field
          name="projectSummary"
          label="One-line summary (20–200 chars)"
          required
          error={fieldErrors.projectSummary}
        >
          <input
            className="w-full rounded border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 focus:outline-none focus-visible:border-violet-500 focus-visible:ring-2 focus-visible:ring-violet-500 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100"
            value={form.projectSummary}
            onChange={(e) => setForm((f) => ({ ...f, projectSummary: e.target.value }))}
          />
        </Field>

        <Field name="projectType" label="Project type" required error={fieldErrors.projectType}>
          <select
            className="w-full rounded border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 focus:outline-none focus-visible:border-violet-500 focus-visible:ring-2 focus-visible:ring-violet-500 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100"
            value={form.projectType}
            onChange={(e) => setForm((f) => ({ ...f, projectType: e.target.value }))}
          >
            <option value="">{REQUIRED_SELECT_PLACEHOLDER}</option>
            {PROJECT_TYPES.map((v) => (
              <option key={v} value={v}>
                {v}
              </option>
            ))}
          </select>
        </Field>

        <Field name="targetAudience" label="Target audience" required error={fieldErrors.targetAudience}>
          <select
            className="w-full rounded border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 focus:outline-none focus-visible:border-violet-500 focus-visible:ring-2 focus-visible:ring-violet-500 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100"
            value={form.targetAudience}
            onChange={(e) => setForm((f) => ({ ...f, targetAudience: e.target.value }))}
          >
            <option value="">{REQUIRED_SELECT_PLACEHOLDER}</option>
            {TARGET_AUDIENCES.map((v) => (
              <option key={v} value={v}>
                {v}
              </option>
            ))}
          </select>
        </Field>

        {form.targetAudience === 'other' ? (
          <Field
            name="targetAudienceOther"
            label="Audience detail"
            required
            error={fieldErrors.targetAudienceOther}
          >
            <input
              className="w-full rounded border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 focus:outline-none focus-visible:border-violet-500 focus-visible:ring-2 focus-visible:ring-violet-500 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100"
              maxLength={200}
              value={form.targetAudienceOther}
              onChange={(e) => setForm((f) => ({ ...f, targetAudienceOther: e.target.value }))}
            />
          </Field>
        ) : null}

        <Field
          name="projectDescription"
          label="Project description (min 100 chars)"
          required
          error={fieldErrors.projectDescription}
        >
          <textarea
            className="min-h-[160px] w-full rounded border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 focus:outline-none focus-visible:border-violet-500 focus-visible:ring-2 focus-visible:ring-violet-500 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100"
            value={form.projectDescription}
            onChange={(e) => setForm((f) => ({ ...f, projectDescription: e.target.value }))}
          />
        </Field>

        <Field
          name="deliverablesText"
          label="Deliverables (one per line, 3–8)"
          required
          error={fieldErrors.deliverablesText}
        >
          <textarea
            className="min-h-[120px] w-full rounded border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 focus:outline-none focus-visible:border-violet-500 focus-visible:ring-2 focus-visible:ring-violet-500 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100"
            value={form.deliverablesText}
            onChange={(e) => setForm((f) => ({ ...f, deliverablesText: e.target.value }))}
          />
        </Field>

        <Field name="deliveryUrgency" label="Delivery urgency" required error={fieldErrors.deliveryUrgency}>
          <select
            className="w-full rounded border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 focus:outline-none focus-visible:border-violet-500 focus-visible:ring-2 focus-visible:ring-violet-500 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100"
            value={form.deliveryUrgency}
            onChange={(e) => setForm((f) => ({ ...f, deliveryUrgency: e.target.value }))}
          >
            <option value="">{REQUIRED_SELECT_PLACEHOLDER}</option>
            {DELIVERY_URGENCY.map((v) => (
              <option key={v} value={v}>
                {v}
              </option>
            ))}
          </select>
        </Field>

        {needsTargetDate ? (
          <Field name="targetDate" label="Target date" required error={fieldErrors.targetDate}>
            <input
              type="date"
              className="w-full rounded border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 focus:outline-none focus-visible:border-violet-500 focus-visible:ring-2 focus-visible:ring-violet-500 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100"
              value={form.targetDate}
              onChange={(e) => setForm((f) => ({ ...f, targetDate: e.target.value }))}
            />
          </Field>
        ) : null}

        <Field name="dataSensitivity" label="Data sensitivity" required error={fieldErrors.dataSensitivity}>
          <select
            className="w-full rounded border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 focus:outline-none focus-visible:border-violet-500 focus-visible:ring-2 focus-visible:ring-violet-500 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100"
            value={form.dataSensitivity}
            onChange={(e) => setForm((f) => ({ ...f, dataSensitivity: e.target.value }))}
          >
            <option value="">{REQUIRED_SELECT_PLACEHOLDER}</option>
            {DATA_SENS.map((v) => (
              <option key={v} value={v}>
                {v}
              </option>
            ))}
          </select>
        </Field>

        <Field name="detailLevel" label="Depth of estimate" required error={fieldErrors.detailLevel}>
          <select
            className="w-full rounded border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 focus:outline-none focus-visible:border-violet-500 focus-visible:ring-2 focus-visible:ring-violet-500 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100"
            value={form.detailLevel}
            onChange={(e) => setForm((f) => ({ ...f, detailLevel: e.target.value }))}
          >
            <option value="">{REQUIRED_SELECT_PLACEHOLDER}</option>
            {DETAIL.map((v) => (
              <option key={v} value={v}>
                {v}
              </option>
            ))}
          </select>
        </Field>

        <Field name="outputFormat" label="Output format" required error={fieldErrors.outputFormat}>
          <select
            className="w-full rounded border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 focus:outline-none focus-visible:border-violet-500 focus-visible:ring-2 focus-visible:ring-violet-500 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100"
            value={form.outputFormat}
            onChange={(e) => setForm((f) => ({ ...f, outputFormat: e.target.value }))}
          >
            <option value="">{REQUIRED_SELECT_PLACEHOLDER}</option>
            {OUTPUT.map((v) => (
              <option key={v} value={v}>
                {v}
              </option>
            ))}
          </select>
        </Field>

        <Field name="attachments" label="Attachments (optional, max 3, .txt / .md / .pdf)" error={fieldErrors.attachments}>
          <input
            type="file"
            multiple
            accept=".txt,.md,.pdf,text/plain,text/markdown,application/pdf"
            className="text-sm file:mr-3 file:rounded file:border-0 file:bg-slate-200 file:px-3 file:py-1.5 file:text-slate-900 file:hover:bg-slate-300 dark:file:bg-slate-700 dark:file:text-slate-100 dark:file:hover:bg-slate-600"
            onChange={(e) => setFileList(Array.from(e.target.files ?? []).slice(0, 3))}
          />
        </Field>

        <details
          className="rounded border border-slate-200 bg-slate-50/90 p-4 dark:border-slate-800 dark:bg-slate-900/40"
          open={moreDetailsOpen}
          onToggle={(e) => setMoreDetailsOpen(e.currentTarget.open)}
        >
          <summary className="cursor-pointer text-sm font-medium text-slate-800 dark:text-slate-200">More details</summary>
          <div className="mt-4 space-y-4">
            <Field name="outOfScopeText" label="Out of scope (optional, one per line)" error={fieldErrors.outOfScopeText}>
              <textarea
                className="min-h-[80px] w-full rounded border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 focus:outline-none focus-visible:border-violet-500 focus-visible:ring-2 focus-visible:ring-violet-500 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100"
                value={form.outOfScopeText}
                onChange={(e) => setForm((f) => ({ ...f, outOfScopeText: e.target.value }))}
              />
            </Field>

            <Field name="deliveryApproach" label="Delivery approach (optional)" error={fieldErrors.deliveryApproach}>
              <select
                className="w-full rounded border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 focus:outline-none focus-visible:border-violet-500 focus-visible:ring-2 focus-visible:ring-violet-500 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100"
                value={form.deliveryApproach}
                onChange={(e) => setForm((f) => ({ ...f, deliveryApproach: e.target.value }))}
              >
                {DELIVERY_APPROACH.map((v) => (
                  <option key={v || 'none'} value={v}>
                    {v || '(none)'}
                  </option>
                ))}
              </select>
            </Field>

            <Field
              name="integrationCategories"
              label="Integration categories (hold Cmd/Ctrl)"
              error={fieldErrors.integrationCategories}
            >
              <select
                multiple
                className="min-h-[120px] w-full rounded border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 focus:outline-none focus-visible:border-violet-500 focus-visible:ring-2 focus-visible:ring-violet-500 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100"
                value={form.integrationCategories}
                onChange={(e) => {
                  const selected = Array.from(e.target.selectedOptions).map((o) => o.value)
                  setForm((f) => ({
                    ...f,
                    integrationCategories: selected as typeof f.integrationCategories,
                  }))
                }}
              >
                {INTEGRATION_ALL.map((v) => (
                  <option key={v} value={v}>
                    {v}
                  </option>
                ))}
              </select>
            </Field>

            <Field
              name="integrationCustomText"
              label="Custom integrations (optional, one per line)"
              hint="One integration per line. Each non-empty line must be between 20 and 300 characters."
              error={fieldErrors.integrationCustomText}
            >
              <textarea
                className="min-h-[60px] w-full rounded border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 focus:outline-none focus-visible:border-violet-500 focus-visible:ring-2 focus-visible:ring-violet-500 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100"
                value={form.integrationCustomText}
                onChange={(e) => setForm((f) => ({ ...f, integrationCustomText: e.target.value }))}
              />
            </Field>

            <Field name="industry" label="Industry (optional)" error={fieldErrors.industry}>
              <select
                className="w-full rounded border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 focus:outline-none focus-visible:border-violet-500 focus-visible:ring-2 focus-visible:ring-violet-500 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100"
                value={form.industry}
                onChange={(e) => setForm((f) => ({ ...f, industry: e.target.value }))}
              >
                {INDUSTRIES.map((v) => (
                  <option key={v || 'none'} value={v}>
                    {v || '(none)'}
                  </option>
                ))}
              </select>
            </Field>

            {form.industry === 'other' ? (
              <Field name="industryOther" label="Industry detail" required error={fieldErrors.industryOther}>
                <input
                  className="w-full rounded border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 focus:outline-none focus-visible:border-violet-500 focus-visible:ring-2 focus-visible:ring-violet-500 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100"
                  maxLength={80}
                  value={form.industryOther}
                  onChange={(e) => setForm((f) => ({ ...f, industryOther: e.target.value }))}
                />
              </Field>
            ) : null}

            <Field name="hostingConstraints" label="Hosting constraints (optional)" error={fieldErrors.hostingConstraints}>
              <select
                multiple
                className="min-h-[100px] w-full rounded border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 focus:outline-none focus-visible:border-violet-500 focus-visible:ring-2 focus-visible:ring-violet-500 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100"
                value={form.hostingConstraints}
                onChange={(e) => {
                  const selected = Array.from(e.target.selectedOptions).map((o) => o.value)
                  setForm((f) => ({
                    ...f,
                    hostingConstraints: selected as typeof f.hostingConstraints,
                  }))
                }}
              >
                {HOSTING_ALL.map((v) => (
                  <option key={v} value={v}>
                    {v}
                  </option>
                ))}
              </select>
            </Field>

            <Field name="hostingNotes" label="Hosting notes (optional)" error={fieldErrors.hostingNotes}>
              <input
                className="w-full rounded border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 focus:outline-none focus-visible:border-violet-500 focus-visible:ring-2 focus-visible:ring-violet-500 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100"
                maxLength={200}
                value={form.hostingNotes}
                onChange={(e) => setForm((f) => ({ ...f, hostingNotes: e.target.value }))}
              />
            </Field>

            <Field name="teamContext" label="Team context (optional)" error={fieldErrors.teamContext}>
              <select
                className="w-full rounded border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 focus:outline-none focus-visible:border-violet-500 focus-visible:ring-2 focus-visible:ring-violet-500 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100"
                value={form.teamContext}
                onChange={(e) => setForm((f) => ({ ...f, teamContext: e.target.value }))}
              >
                {TEAM_CONTEXT.map((v) => (
                  <option key={v || 'none'} value={v}>
                    {v || '(none)'}
                  </option>
                ))}
              </select>
            </Field>

            <Field name="uiLanguages" label="UI languages (optional, max 3)" error={fieldErrors.uiLanguages}>
              <select
                multiple
                className="min-h-[90px] w-full rounded border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 focus:outline-none focus-visible:border-violet-500 focus-visible:ring-2 focus-visible:ring-violet-500 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100"
                value={form.uiLanguages}
                onChange={(e) => {
                  const selected = Array.from(e.target.selectedOptions).map((o) => o.value)
                  setForm((f) => ({
                    ...f,
                    uiLanguages: selected.slice(0, 3) as typeof f.uiLanguages,
                  }))
                }}
              >
                {UI_LANG.map((v) => (
                  <option key={v} value={v}>
                    {v}
                  </option>
                ))}
              </select>
            </Field>

            <Field name="riskLevel" label="Risk level (optional)" error={fieldErrors.riskLevel}>
              <select
                className="w-full rounded border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 focus:outline-none focus-visible:border-violet-500 focus-visible:ring-2 focus-visible:ring-violet-500 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100"
                value={form.riskLevel}
                onChange={(e) => setForm((f) => ({ ...f, riskLevel: e.target.value }))}
              >
                {RISK.map((v) => (
                  <option key={v || 'none'} value={v}>
                    {v || '(none)'}
                  </option>
                ))}
              </select>
            </Field>

            <Field
              name="externalDependenciesText"
              label="External dependencies (optional)"
              error={fieldErrors.externalDependenciesText}
            >
              <textarea
                className="min-h-[60px] w-full rounded border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 focus:outline-none focus-visible:border-violet-500 focus-visible:ring-2 focus-visible:ring-violet-500 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100"
                value={form.externalDependenciesText}
                onChange={(e) => setForm((f) => ({ ...f, externalDependenciesText: e.target.value }))}
              />
            </Field>

            <Field
              name="preprocessing"
              label="Preprocessing (optional, default none)"
              error={fieldErrors.preprocessing}
            >
              <select
                className="w-full rounded border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 focus:outline-none focus-visible:border-violet-500 focus-visible:ring-2 focus-visible:ring-violet-500 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100"
                value={form.preprocessing}
                onChange={(e) => setForm((f) => ({ ...f, preprocessing: e.target.value }))}
              >
                <option value="">Use default (none)</option>
                {PREPROCESSING.map((v) => (
                  <option key={v} value={v}>
                    {v}
                  </option>
                ))}
              </select>
            </Field>

            <label className="flex items-center gap-2 text-sm text-slate-700 dark:text-slate-300">
              <input
                type="checkbox"
                checked={form.evaluate}
                onChange={(e) => setForm((f) => ({ ...f, evaluate: e.target.checked }))}
              />
              Structure evaluation (evaluate)
            </label>
          </div>
        </details>

        {(clientError || fieldErrors._form) ? (
          <div
            role="alert"
            className="rounded-lg border border-amber-300/80 bg-amber-50/90 px-4 py-3 text-sm text-amber-950 dark:border-amber-800/70 dark:bg-amber-950/50 dark:text-amber-100"
          >
            {clientError ? <p>{clientError}</p> : null}
            {fieldErrors._form ? <p className={clientError ? 'mt-2' : ''}>{fieldErrors._form}</p> : null}
          </div>
        ) : null}

        <div className="flex flex-wrap gap-3">
          <button
            type="submit"
            disabled={loading}
            className="rounded bg-violet-600 px-4 py-2 text-sm font-medium text-white hover:bg-violet-500 disabled:opacity-50"
          >
            {loading ? 'Running…' : 'Generate estimate'}
          </button>
          <button
            type="button"
            onClick={() => cancel()}
            className="rounded border border-slate-300 px-4 py-2 text-sm text-slate-800 hover:bg-slate-100 dark:border-slate-600 dark:text-slate-200 dark:hover:bg-slate-800"
          >
            Cancel request
          </button>
        </div>
      </form>

      {structuredResult ? (
        <section className="mt-10 border-t border-slate-200 pt-8 dark:border-slate-800">
          <h2 className="text-xl font-bold tracking-tight text-slate-900 dark:text-white">Estimate (structured)</h2>
          <StructuredEstimateSummary data={structuredResult} />
        </section>
      ) : markdown ? (
        <section className="mt-10 border-t border-slate-200 pt-8 dark:border-slate-800">
          <h2 className="text-lg font-semibold text-slate-900 dark:text-white">Estimate</h2>
          <article className="mt-4 max-w-none text-left text-sm leading-relaxed text-slate-800 dark:text-slate-200 [&_a]:text-violet-700 [&_code]:rounded [&_code]:bg-slate-200 [&_code]:px-1 [&_code]:text-slate-900 [&_h1]:text-xl [&_h2]:text-lg [&_ul]:list-disc [&_ul]:pl-5 dark:[&_a]:text-violet-300 dark:[&_code]:bg-slate-800 dark:[&_code]:text-slate-100">
            <ReactMarkdown>{markdown}</ReactMarkdown>
          </article>
        </section>
      ) : null}

      {doneMeta && typeof doneMeta.usage === 'object' && doneMeta.usage !== null ? (
        <p className="mt-4 text-xs text-slate-500 dark:text-slate-500">
          Tokens: {JSON.stringify(doneMeta.usage)}
        </p>
      ) : null}
    </div>
  )
}

function Field({
  name,
  label,
  error,
  hint,
  required,
  children,
}: {
  name: string
  label: string
  error?: string
  hint?: string
  /** When true, label shows a trailing ` *` and the control gets `aria-required`. */
  required?: boolean
  children: ReactElement<Record<string, unknown>>
}) {
  const hintId = `${name}-hint`
  const errId = `${name}-error`
  const invalid = Boolean(error)
  const describedByParts: string[] = []
  if (hint) {
    describedByParts.push(hintId)
  }
  if (invalid) {
    describedByParts.push(errId)
  }
  const describedBy = describedByParts.length > 0 ? describedByParts.join(' ') : undefined
  const childProps = children.props as { className?: string }
  const childClass = childProps.className
  const child = cloneElement(children, {
    id: name,
    name,
    'aria-invalid': invalid ? true : undefined,
    'aria-describedby': describedBy,
    'aria-required': required ? true : undefined,
    className: invalid ? [childClass, CONTROL_ERR_RING].filter(Boolean).join(' ') : childClass,
  } as Record<string, unknown>)
  const labelText = required ? `${label} *` : label
  return (
    <div className="space-y-0">
      <label htmlFor={name} className="mb-1 block text-xs font-medium uppercase tracking-wide text-slate-500 dark:text-slate-400">
        {labelText}
      </label>
      {hint ? (
        <p id={hintId} className="mb-1.5 text-xs text-slate-500 dark:text-slate-400">
          {hint}
        </p>
      ) : null}
      {child}
      {error ? (
        <p id={errId} role="alert" className="mt-1.5 text-sm text-red-600 dark:text-red-400">
          {error}
        </p>
      ) : null}
    </div>
  )
}
