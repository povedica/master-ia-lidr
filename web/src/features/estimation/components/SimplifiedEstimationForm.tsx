import type { FormEvent } from 'react'

import {
  humanizeEnum,
  INDUSTRIES,
  PROJECT_TYPES,
  REQUIRED_SELECT_PLACEHOLDER,
  TARGET_AUDIENCES,
  TRANSCRIPT_MAX,
} from '../lib/estimationConstants'
import type { SimplifiedFormValues } from '../lib/simplifiedForm'

import { Field, INPUT_CLASS } from './Field'

const CARD_CLASS =
  'rounded-xl border border-slate-200 bg-white p-6 shadow-sm dark:border-slate-700 dark:bg-slate-900'

export function SimplifiedEstimationForm({
  form,
  fieldErrors,
  formSummary,
  fileList,
  disabled,
  submitting,
  onChange,
  onFilesChange,
  onSubmit,
}: {
  form: SimplifiedFormValues
  fieldErrors: Record<string, string>
  formSummary: string | null
  fileList: File[]
  disabled: boolean
  submitting: boolean
  onChange: (patch: Partial<SimplifiedFormValues>) => void
  onFilesChange: (files: File[]) => void
  onSubmit: (ev: FormEvent) => void
}) {
  return (
    <section className={CARD_CLASS}>
      <h2 className="text-lg font-semibold text-slate-900 dark:text-white">Project information</h2>
      <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">
        Provide essential project details for the estimator.
      </p>
      {formSummary ? (
        <p role="alert" className="mt-4 rounded-md border border-amber-300 bg-amber-50 px-3 py-2 text-sm text-amber-900 dark:border-amber-800 dark:bg-amber-950 dark:text-amber-100">
          {formSummary}
        </p>
      ) : null}
      <form onSubmit={onSubmit} className="mt-6 space-y-5" aria-busy={submitting}>
        <Field name="projectName" label="Project name" required error={fieldErrors.projectName}>
          <input
            className={INPUT_CLASS}
            maxLength={120}
            disabled={disabled}
            value={form.projectName}
            onChange={(e) => onChange({ projectName: e.target.value })}
          />
        </Field>

        <Field
          name="oneLineSummary"
          label="One-line summary"
          hint="Optional elevator pitch."
          error={fieldErrors.oneLineSummary}
        >
          <input
            className={INPUT_CLASS}
            maxLength={200}
            disabled={disabled}
            value={form.oneLineSummary ?? ''}
            onChange={(e) => onChange({ oneLineSummary: e.target.value })}
          />
        </Field>

        <Field name="projectType" label="Project type" required error={fieldErrors.projectType}>
          <select
            className={INPUT_CLASS}
            disabled={disabled}
            value={form.projectType}
            onChange={(e) => onChange({ projectType: e.target.value })}
          >
            <option value="">{REQUIRED_SELECT_PLACEHOLDER}</option>
            {PROJECT_TYPES.map((v) => (
              <option key={v} value={v}>
                {humanizeEnum(v)}
              </option>
            ))}
          </select>
        </Field>

        <Field
          name="transcript"
          label="Transcript"
          required
          hint="Paste the main project description, discovery notes, or meeting transcript."
          error={fieldErrors.transcript}
        >
          <textarea
            className={`${INPUT_CLASS} min-h-[200px] lg:min-h-[220px]`}
            maxLength={TRANSCRIPT_MAX}
            disabled={disabled}
            value={form.transcript}
            onChange={(e) => onChange({ transcript: e.target.value })}
          />
        </Field>
        <p className="-mt-3 text-right text-xs text-slate-500" aria-live="polite">
          {form.transcript.length} / {TRANSCRIPT_MAX}
        </p>

        <Field name="targetAudience" label="Target audience" required error={fieldErrors.targetAudience}>
          <select
            className={INPUT_CLASS}
            disabled={disabled}
            value={form.targetAudience}
            onChange={(e) => onChange({ targetAudience: e.target.value })}
          >
            <option value="">{REQUIRED_SELECT_PLACEHOLDER}</option>
            {TARGET_AUDIENCES.map((v) => (
              <option key={v} value={v}>
                {humanizeEnum(v)}
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
              className={INPUT_CLASS}
              maxLength={200}
              disabled={disabled}
              value={form.targetAudienceOther ?? ''}
              onChange={(e) => onChange({ targetAudienceOther: e.target.value })}
            />
          </Field>
        ) : null}

        <Field name="industry" label="Industry" error={fieldErrors.industry}>
          <select
            className={INPUT_CLASS}
            disabled={disabled}
            value={form.industry ?? ''}
            onChange={(e) => onChange({ industry: e.target.value })}
          >
            <option value="">Optional</option>
            {INDUSTRIES.filter((v) => v !== '').map((v) => (
              <option key={v} value={v}>
                {humanizeEnum(v)}
              </option>
            ))}
          </select>
        </Field>

        <Field name="attachments" label="Attachments" error={fieldErrors.attachments}>
          <input
            type="file"
            multiple
            disabled={disabled}
            className="block w-full text-sm text-slate-600 file:mr-4 file:rounded file:border-0 file:bg-teal-50 file:px-3 file:py-2 file:text-sm file:font-medium file:text-teal-800 dark:text-slate-300 dark:file:bg-teal-950 dark:file:text-teal-200"
            onChange={(e) => onFilesChange(e.target.files ? Array.from(e.target.files) : [])}
          />
        </Field>
        {fileList.length > 0 || form.attachments.length > 0 ? (
          <ul className="-mt-2 space-y-1 text-xs text-slate-500">
            {fileList.map((f) => (
              <li key={`${f.name}-${f.size}`}>
                {f.name} ({Math.round(f.size / 1024)} KiB)
              </li>
            ))}
            {fileList.length === 0
              ? form.attachments.map((a) => (
                  <li key={a.file_id}>
                    {a.name} <span className="text-slate-400">(saved in session)</span>
                  </li>
                ))
              : null}
          </ul>
        ) : null}

        <Field
          name="additionalExtraInfo"
          label="Additional extra info"
          hint="Optional. Constraints, links, or context that does not belong in the transcript."
          error={fieldErrors.additionalExtraInfo}
        >
          <textarea
            className={`${INPUT_CLASS} min-h-[88px]`}
            maxLength={4000}
            disabled={disabled}
            value={form.additionalExtraInfo ?? ''}
            onChange={(e) => onChange({ additionalExtraInfo: e.target.value })}
          />
        </Field>

        <button
          type="submit"
          disabled={disabled || submitting}
          className="rounded bg-teal-600 px-4 py-2.5 text-sm font-medium text-white hover:bg-teal-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-teal-500 focus-visible:ring-offset-2 disabled:opacity-50 dark:hover:bg-teal-500"
        >
          {submitting ? 'Generating…' : 'Generate estimate'}
        </button>
      </form>
    </section>
  )
}
