import { type FormEvent, useMemo, useState } from 'react'
import type { ReactNode } from 'react'
import ReactMarkdown from 'react-markdown'
import { ZodError } from 'zod'

import { useEstimateStream } from '../hooks/useEstimateStream'
import { estimateStreamUrl } from '../api/estimateApi'
import { filesToAttachments } from '../lib/fileToBase64'
import {
  mapEstimationFormToRequestBody,
  parseEstimationForm,
  type EstimationFormValues,
} from '../lib/requestMapper'

const DEFAULT_PROJECT_DESCRIPTION =
  'The client needs a responsive web application for authenticated partners to submit ' +
  'structured tickets, follow approval workflows, and view status dashboards. ' +
  'Integrations with existing CRM are out of scope for the first milestone. ' +
  'x'.repeat(30)

const DEFAULT_DELIVERABLES = [
  'Partner authentication with SSO and role-based access control',
  'Configurable ticket intake forms and commenting threads',
  'Operations dashboards with CSV export and saved filters',
].join('\n')

function buildInitialForm(): EstimationFormValues {
  return {
    projectName: '',
    projectSummary:
      'B2B partner portal for support intake, SLA tracking, and quarterly reporting.',
    projectType: 'web_saas',
    targetAudience: 'b2b_enterprise',
    targetAudienceOther: '',
    industry: '',
    industryOther: '',
    projectDescription: DEFAULT_PROJECT_DESCRIPTION,
    deliverablesText: DEFAULT_DELIVERABLES,
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

export function EstimationWorkbench() {
  const { markdown, loading, error, doneMeta, run, cancel } = useEstimateStream()
  const [form, setForm] = useState<EstimationFormValues>(buildInitialForm)
  const [clientError, setClientError] = useState<string | null>(null)
  const [fileList, setFileList] = useState<File[]>([])

  const needsTargetDate = useMemo(
    () => form.deliveryUrgency === 'fixed_date' || form.deliveryUrgency === 'critical',
    [form.deliveryUrgency],
  )

  async function onSubmit(ev: FormEvent) {
    ev.preventDefault()
    setClientError(null)
    let attachments = form.attachments
    try {
      if (fileList.length > 0) {
        attachments = await filesToAttachments(fileList)
      }
    } catch (exc) {
      setClientError(exc instanceof Error ? exc.message : 'Invalid attachments.')
      return
    }

    const raw = { ...form, attachments }
    try {
      const parsed = parseEstimationForm(raw)
      const body = mapEstimationFormToRequestBody(parsed)
      void run(body)
    } catch (exc) {
      if (exc instanceof ZodError) {
        setClientError(
          exc.issues.map((issue) => `${issue.path.join('.') || 'form'}: ${issue.message}`).join('\n'),
        )
        return
      }
      setClientError(exc instanceof Error ? exc.message : 'Validation failed.')
    }
  }

  return (
    <div className="mx-auto max-w-3xl px-4 py-8 text-left text-slate-100">
      <header className="mb-8 border-b border-slate-800 pb-6">
        <h1 className="text-2xl font-semibold text-white">Estimador CAG</h1>
        <p className="mt-2 text-sm text-slate-400">
          Guided estimation form. Output streams from{' '}
          <code className="rounded bg-slate-800 px-1 py-0.5 text-xs">{estimateStreamUrl()}</code>.
        </p>
      </header>

      <form onSubmit={onSubmit} className="space-y-6">
        <Field label="Project name (optional)">
          <input
            className="w-full rounded border border-slate-700 bg-slate-900 px-3 py-2 text-sm"
            maxLength={120}
            value={form.projectName}
            onChange={(e) => setForm((f) => ({ ...f, projectName: e.target.value }))}
          />
        </Field>

        <Field label="One-line summary (20–200 chars)">
          <input
            className="w-full rounded border border-slate-700 bg-slate-900 px-3 py-2 text-sm"
            value={form.projectSummary}
            onChange={(e) => setForm((f) => ({ ...f, projectSummary: e.target.value }))}
          />
        </Field>

        <Field label="Project type">
          <select
            className="w-full rounded border border-slate-700 bg-slate-900 px-3 py-2 text-sm"
            value={form.projectType}
            onChange={(e) =>
              setForm((f) => ({ ...f, projectType: e.target.value as (typeof PROJECT_TYPES)[number] }))
            }
          >
            {PROJECT_TYPES.map((v) => (
              <option key={v} value={v}>
                {v}
              </option>
            ))}
          </select>
        </Field>

        <Field label="Target audience">
          <select
            className="w-full rounded border border-slate-700 bg-slate-900 px-3 py-2 text-sm"
            value={form.targetAudience}
            onChange={(e) =>
              setForm((f) => ({
                ...f,
                targetAudience: e.target.value as (typeof TARGET_AUDIENCES)[number],
              }))
            }
          >
            {TARGET_AUDIENCES.map((v) => (
              <option key={v} value={v}>
                {v}
              </option>
            ))}
          </select>
        </Field>

        {form.targetAudience === 'other' ? (
          <Field label="Audience detail (required)">
            <input
              className="w-full rounded border border-slate-700 bg-slate-900 px-3 py-2 text-sm"
              maxLength={200}
              value={form.targetAudienceOther}
              onChange={(e) => setForm((f) => ({ ...f, targetAudienceOther: e.target.value }))}
            />
          </Field>
        ) : null}

        <Field label="Project description (min 100 chars)">
          <textarea
            className="min-h-[160px] w-full rounded border border-slate-700 bg-slate-900 px-3 py-2 text-sm"
            value={form.projectDescription}
            onChange={(e) => setForm((f) => ({ ...f, projectDescription: e.target.value }))}
          />
        </Field>

        <Field label="Deliverables (one per line, 3–8)">
          <textarea
            className="min-h-[120px] w-full rounded border border-slate-700 bg-slate-900 px-3 py-2 text-sm"
            value={form.deliverablesText}
            onChange={(e) => setForm((f) => ({ ...f, deliverablesText: e.target.value }))}
          />
        </Field>

        <Field label="Delivery urgency">
          <select
            className="w-full rounded border border-slate-700 bg-slate-900 px-3 py-2 text-sm"
            value={form.deliveryUrgency}
            onChange={(e) =>
              setForm((f) => ({
                ...f,
                deliveryUrgency: e.target.value as (typeof DELIVERY_URGENCY)[number],
              }))
            }
          >
            {DELIVERY_URGENCY.map((v) => (
              <option key={v} value={v}>
                {v}
              </option>
            ))}
          </select>
        </Field>

        {needsTargetDate ? (
          <Field label="Target date">
            <input
              type="date"
              className="w-full rounded border border-slate-700 bg-slate-900 px-3 py-2 text-sm"
              value={form.targetDate}
              onChange={(e) => setForm((f) => ({ ...f, targetDate: e.target.value }))}
            />
          </Field>
        ) : null}

        <Field label="Data sensitivity">
          <select
            className="w-full rounded border border-slate-700 bg-slate-900 px-3 py-2 text-sm"
            value={form.dataSensitivity}
            onChange={(e) =>
              setForm((f) => ({
                ...f,
                dataSensitivity: e.target.value as (typeof DATA_SENS)[number],
              }))
            }
          >
            {DATA_SENS.map((v) => (
              <option key={v} value={v}>
                {v}
              </option>
            ))}
          </select>
        </Field>

        <Field label="Depth of estimate">
          <select
            className="w-full rounded border border-slate-700 bg-slate-900 px-3 py-2 text-sm"
            value={form.detailLevel}
            onChange={(e) =>
              setForm((f) => ({ ...f, detailLevel: e.target.value as (typeof DETAIL)[number] }))
            }
          >
            {DETAIL.map((v) => (
              <option key={v} value={v}>
                {v}
              </option>
            ))}
          </select>
        </Field>

        <Field label="Output format">
          <select
            className="w-full rounded border border-slate-700 bg-slate-900 px-3 py-2 text-sm"
            value={form.outputFormat}
            onChange={(e) =>
              setForm((f) => ({ ...f, outputFormat: e.target.value as (typeof OUTPUT)[number] }))
            }
          >
            {OUTPUT.map((v) => (
              <option key={v} value={v}>
                {v}
              </option>
            ))}
          </select>
        </Field>

        <Field label="Attachments (optional, max 3, .txt / .md / .pdf)">
          <input
            type="file"
            multiple
            accept=".txt,.md,.pdf,text/plain,text/markdown,application/pdf"
            className="text-sm file:mr-3 file:rounded file:border-0 file:bg-slate-700 file:px-3 file:py-1.5 file:text-slate-100"
            onChange={(e) => setFileList(Array.from(e.target.files ?? []).slice(0, 3))}
          />
        </Field>

        <details className="rounded border border-slate-800 bg-slate-900/40 p-4">
          <summary className="cursor-pointer text-sm font-medium text-slate-200">More details</summary>
          <div className="mt-4 space-y-4">
            <Field label="Out of scope (optional, one per line)">
              <textarea
                className="min-h-[80px] w-full rounded border border-slate-700 bg-slate-900 px-3 py-2 text-sm"
                value={form.outOfScopeText}
                onChange={(e) => setForm((f) => ({ ...f, outOfScopeText: e.target.value }))}
              />
            </Field>

            <Field label="Delivery approach (optional)">
              <select
                className="w-full rounded border border-slate-700 bg-slate-900 px-3 py-2 text-sm"
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

            <Field label="Integration categories (hold Cmd/Ctrl)">
              <select
                multiple
                className="min-h-[120px] w-full rounded border border-slate-700 bg-slate-900 px-3 py-2 text-sm"
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

            <Field label="Custom integrations (optional, one per line)">
              <textarea
                className="min-h-[60px] w-full rounded border border-slate-700 bg-slate-900 px-3 py-2 text-sm"
                value={form.integrationCustomText}
                onChange={(e) => setForm((f) => ({ ...f, integrationCustomText: e.target.value }))}
              />
            </Field>

            <Field label="Industry (optional)">
              <select
                className="w-full rounded border border-slate-700 bg-slate-900 px-3 py-2 text-sm"
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
              <Field label="Industry detail (required)">
                <input
                  className="w-full rounded border border-slate-700 bg-slate-900 px-3 py-2 text-sm"
                  maxLength={80}
                  value={form.industryOther}
                  onChange={(e) => setForm((f) => ({ ...f, industryOther: e.target.value }))}
                />
              </Field>
            ) : null}

            <Field label="Hosting constraints (optional)">
              <select
                multiple
                className="min-h-[100px] w-full rounded border border-slate-700 bg-slate-900 px-3 py-2 text-sm"
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

            <Field label="Hosting notes (optional)">
              <input
                className="w-full rounded border border-slate-700 bg-slate-900 px-3 py-2 text-sm"
                maxLength={200}
                value={form.hostingNotes}
                onChange={(e) => setForm((f) => ({ ...f, hostingNotes: e.target.value }))}
              />
            </Field>

            <Field label="Team context (optional)">
              <select
                className="w-full rounded border border-slate-700 bg-slate-900 px-3 py-2 text-sm"
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

            <Field label="UI languages (optional, max 3)">
              <select
                multiple
                className="min-h-[90px] w-full rounded border border-slate-700 bg-slate-900 px-3 py-2 text-sm"
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

            <Field label="Risk level (optional)">
              <select
                className="w-full rounded border border-slate-700 bg-slate-900 px-3 py-2 text-sm"
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

            <Field label="External dependencies (optional)">
              <textarea
                className="min-h-[60px] w-full rounded border border-slate-700 bg-slate-900 px-3 py-2 text-sm"
                value={form.externalDependenciesText}
                onChange={(e) => setForm((f) => ({ ...f, externalDependenciesText: e.target.value }))}
              />
            </Field>

            <Field label="Preprocessing">
              <select
                className="w-full rounded border border-slate-700 bg-slate-900 px-3 py-2 text-sm"
                value={form.preprocessing}
                onChange={(e) =>
                  setForm((f) => ({
                    ...f,
                    preprocessing: e.target.value as (typeof PREPROCESSING)[number],
                  }))
                }
              >
                {PREPROCESSING.map((v) => (
                  <option key={v} value={v}>
                    {v}
                  </option>
                ))}
              </select>
            </Field>

            <label className="flex items-center gap-2 text-sm text-slate-300">
              <input
                type="checkbox"
                checked={form.evaluate}
                onChange={(e) => setForm((f) => ({ ...f, evaluate: e.target.checked }))}
              />
              Structure evaluation (evaluate)
            </label>
          </div>
        </details>

        <div className="flex flex-wrap gap-3">
          <button
            type="submit"
            disabled={loading}
            className="rounded bg-violet-600 px-4 py-2 text-sm font-medium text-white hover:bg-violet-500 disabled:opacity-50"
          >
            {loading ? 'Streaming…' : 'Generate estimate'}
          </button>
          <button
            type="button"
            onClick={() => cancel()}
            className="rounded border border-slate-600 px-4 py-2 text-sm text-slate-200 hover:bg-slate-800"
          >
            Cancel stream
          </button>
        </div>
      </form>

      {clientError ? (
        <pre className="mt-6 whitespace-pre-wrap rounded border border-amber-900/60 bg-amber-950/40 p-4 text-sm text-amber-100">
          {clientError}
        </pre>
      ) : null}

      {error ? (
        <pre className="mt-6 whitespace-pre-wrap rounded border border-red-900/60 bg-red-950/40 p-4 text-sm text-red-100">
          {error}
        </pre>
      ) : null}

      {markdown ? (
        <section className="mt-10 border-t border-slate-800 pt-8">
          <h2 className="text-lg font-semibold text-white">Estimate</h2>
          <article className="mt-4 max-w-none text-left text-sm leading-relaxed text-slate-200 [&_a]:text-violet-300 [&_code]:rounded [&_code]:bg-slate-800 [&_code]:px-1 [&_h1]:text-xl [&_h2]:text-lg [&_ul]:list-disc [&_ul]:pl-5">
            <ReactMarkdown>{markdown}</ReactMarkdown>
          </article>
        </section>
      ) : null}

      {doneMeta && typeof doneMeta.usage === 'object' && doneMeta.usage !== null ? (
        <p className="mt-4 text-xs text-slate-500">
          Tokens: {JSON.stringify(doneMeta.usage)}
        </p>
      ) : null}
    </div>
  )
}

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div>
      <label className="mb-1 block text-xs font-medium uppercase tracking-wide text-slate-400">
        {label}
      </label>
      {children}
    </div>
  )
}
