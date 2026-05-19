import { type FormEvent, useCallback, useEffect, useRef, useState } from 'react'
import { ZodError } from 'zod'

import { useSessionEstimate } from '../hooks/useSessionEstimate'
import { filesToAttachmentRefs } from '../lib/attachmentRefs'
import {
  buildInitialSimplifiedForm,
  mapToSessionEstimateBody,
  parseSimplifiedForm,
  SIMPLIFIED_FORM_FIELD_ORDER,
  type SimplifiedFormValues,
} from '../lib/simplifiedForm'
import { humanizeZodIssuesToFieldErrors } from '../lib/validationErrors'

import { EstimateResultPanel } from './EstimateResultPanel'
import { EstimatorHeader } from './EstimatorHeader'
import { ProjectMetadataPanel } from './ProjectMetadataPanel'
import { SimplifiedEstimationForm } from './SimplifiedEstimationForm'

function firstOrderedFieldWithError(
  fieldErrors: Record<string, string>,
  order: readonly string[],
): string | null {
  for (const k of order) {
    if (fieldErrors[k]) {
      return k
    }
  }
  return Object.keys(fieldErrors).find((k) => k !== '_form') ?? null
}

export function EstimationWorkbench({ themeControl }: { themeControl: React.ReactNode }) {
  const {
    sessionId,
    sessionStatus,
    sessionError,
    resetInProgress,
    projectMetadata,
    metadataStatus,
    estimate,
    estimateStatus,
    estimateError,
    warnings,
    bootstrapSession,
    resetConversation,
    submitEstimate,
    clearPanels,
  } = useSessionEstimate()

  const [form, setForm] = useState<SimplifiedFormValues>(buildInitialSimplifiedForm)
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({})
  const [formSummary, setFormSummary] = useState<string | null>(null)
  const [fileList, setFileList] = useState<File[]>([])
  const hadFieldErrorsRef = useRef(false)

  const formDisabled = sessionStatus !== 'ready' || resetInProgress
  const submitting = estimateStatus === 'loading'

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
    const first = firstOrderedFieldWithError(fieldErrors, SIMPLIFIED_FORM_FIELD_ORDER)
    if (!first) {
      return
    }
    const t = window.setTimeout(() => {
      document.getElementById(first)?.scrollIntoView({ behavior: 'smooth', block: 'center' })
      const el = document.getElementById(first)
      if (el instanceof HTMLElement) {
        el.focus()
      }
    }, 100)
    return () => window.clearTimeout(t)
  }, [fieldErrors])

  const handleNewConversation = useCallback(async () => {
    setForm(buildInitialSimplifiedForm())
    setFileList([])
    setFieldErrors({})
    setFormSummary(null)
    clearPanels()
    await resetConversation()
  }, [clearPanels, resetConversation])

  async function onSubmit(ev: FormEvent) {
    ev.preventDefault()
    if (!sessionId) {
      return
    }
    setFormSummary(null)
    setFieldErrors({})

    let attachments = form.attachments
    try {
      if (fileList.length > 0) {
        attachments = await filesToAttachmentRefs(fileList)
      }
    } catch (exc) {
      setFieldErrors({
        attachments: exc instanceof Error ? exc.message : 'Invalid attachments.',
      })
      return
    }

    const raw = { ...form, attachments }
    try {
      const parsed = parseSimplifiedForm(raw)
      const body = mapToSessionEstimateBody(parsed)
      const outcome = await submitEstimate(body)
      if (!outcome.ok) {
        if (outcome.kind === 'validation') {
          setFieldErrors(outcome.fieldErrors)
          setFormSummary(outcome.formSummary ?? null)
          return
        }
        return
      }
    } catch (exc) {
      if (exc instanceof ZodError) {
        setFieldErrors(humanizeZodIssuesToFieldErrors(exc.issues))
        return
      }
      setFormSummary(exc instanceof Error ? exc.message : 'We could not validate the form.')
    }
  }

  return (
    <div className="mx-auto max-w-7xl px-4 py-8 text-left text-slate-900 dark:text-slate-100">
      <EstimatorHeader
        sessionId={sessionId}
        sessionStatus={sessionStatus}
        sessionError={sessionError}
        resetInProgress={resetInProgress}
        onNewConversation={() => void handleNewConversation()}
        onRetrySession={() => void bootstrapSession()}
        themeControl={themeControl}
      />

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(320px,400px)]">
        <SimplifiedEstimationForm
          form={form}
          fieldErrors={fieldErrors}
          formSummary={formSummary}
          fileList={fileList}
          disabled={formDisabled}
          submitting={submitting}
          onChange={(patch) => setForm((f) => ({ ...f, ...patch }))}
          onFilesChange={setFileList}
          onSubmit={onSubmit}
        />
        <ProjectMetadataPanel status={metadataStatus} metadata={projectMetadata} />
      </div>

      {warnings.length > 0 ? (
        <section
          className="mt-6 rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900 dark:border-amber-900 dark:bg-amber-950/50 dark:text-amber-100"
          role="status"
          aria-label="Warnings"
        >
          <h3 className="mb-2 text-sm font-semibold text-amber-950 dark:text-amber-50">Warnings</h3>
          <ul className="list-disc space-y-1 pl-5">
            {warnings.map((w) => (
              <li key={w}>{w}</li>
            ))}
          </ul>
        </section>
      ) : null}

      <div className="mt-6">
        <EstimateResultPanel status={estimateStatus} estimate={estimate} errorMessage={estimateError} />
      </div>
    </div>
  )
}
