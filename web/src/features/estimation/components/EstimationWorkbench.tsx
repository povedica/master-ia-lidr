import { type FormEvent, useCallback, useEffect, useRef, useState } from 'react'
import { ZodError } from 'zod'

import { RagEstimateApiError, runRagEstimate, type RagEstimationResponse } from '../api/ragEstimateApi'
import { useSessionEstimate, type PanelStatus } from '../hooks/useSessionEstimate'
import { assertFilesWithinLimits } from '../lib/attachmentRefs'
import { buildRagQuestion } from '../lib/buildRagQuestion'
import {
  buildInitialSimplifiedForm,
  mapToSessionEstimateBody,
  parseSimplifiedForm,
  payloadToSimplifiedForm,
  SIMPLIFIED_FORM_FIELD_ORDER,
  type SimplifiedFormValues,
} from '../lib/simplifiedForm'
import { humanizeZodIssuesToFieldErrors } from '../lib/validationErrors'

import { EstimateResultPanel } from './EstimateResultPanel'
import { EstimatorHeader } from './EstimatorHeader'
import { ProjectMetadataPanel } from './ProjectMetadataPanel'
import { SessionHistorySidebar } from './SessionHistorySidebar'
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

export function EstimationWorkbench({
  retrievalDebugHref,
  themeControl,
}: {
  retrievalDebugHref?: string
  themeControl: React.ReactNode
}) {
  const {
    sessionId,
    sessionStatus,
    sessionError,
    resetInProgress,
    selectInProgress,
    sessionList,
    sessionListStatus,
    sessionListError,
    projectMetadata,
    metadataStatus,
    estimate,
    estimateStatus,
    estimateError,
    warnings,
    bootstrapSession,
    resetConversation,
    selectSession,
    refreshSessionList,
    submitEstimate,
    clearPanels,
  } = useSessionEstimate()

  const [form, setForm] = useState<SimplifiedFormValues>(buildInitialSimplifiedForm)
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({})
  const [formSummary, setFormSummary] = useState<string | null>(null)
  const [fileList, setFileList] = useState<File[]>([])
  const [ragResponse, setRagResponse] = useState<RagEstimationResponse | null>(null)
  const [ragStatus, setRagStatus] = useState<PanelStatus>('empty')
  const [ragError, setRagError] = useState<string | null>(null)
  const hadFieldErrorsRef = useRef(false)

  const formDisabled = sessionStatus !== 'ready' || resetInProgress || selectInProgress
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

  const handleSelectSession = useCallback(
    async (targetSessionId: string) => {
      if (targetSessionId === sessionId) {
        return
      }
      setFieldErrors({})
      setFormSummary(null)
      setFileList([])
      setRagResponse(null)
      setRagStatus('empty')
      setRagError(null)
      const outcome = await selectSession(targetSessionId)
      if (!outcome.ok) {
        setFormSummary(outcome.message)
        return
      }
      if (outcome.detail.input_payload) {
        setForm(payloadToSimplifiedForm(outcome.detail.input_payload))
      } else {
        setForm(buildInitialSimplifiedForm())
      }
    },
    [selectSession, sessionId],
  )

  const handleNewConversation = useCallback(async () => {
    setForm(buildInitialSimplifiedForm())
    setFileList([])
    setFieldErrors({})
    setFormSummary(null)
    setRagResponse(null)
    setRagStatus('empty')
    setRagError(null)
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

    try {
      if (fileList.length > 0) {
        assertFilesWithinLimits(fileList)
      }
    } catch (exc) {
      setFieldErrors({
        attachments: exc instanceof Error ? exc.message : 'Invalid attachments.',
      })
      return
    }

    const raw = { ...form, attachments: fileList.length > 0 ? [] : form.attachments }
    try {
      const parsed = parseSimplifiedForm(raw)
      const body = mapToSessionEstimateBody(parsed)
      const outcome = await submitEstimate(
        body,
        fileList.length > 0 ? { files: fileList } : undefined,
      )
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

  const handleRunRagEstimate = useCallback(async () => {
    setRagError(null)
    setRagStatus('loading')
    try {
      const question = buildRagQuestion(form)
      if (!question.trim()) {
        setRagStatus('error')
        setRagError('Add a transcript or one-line summary before running RAG estimate.')
        return
      }
      const response = await runRagEstimate({ question })
      setRagResponse(response)
      setRagStatus('available')
    } catch (exc) {
      setRagStatus('error')
      if (exc instanceof RagEstimateApiError && exc.status === 503) {
        setRagError('RAG estimation is temporarily unavailable.')
        return
      }
      setRagError(exc instanceof Error ? exc.message : 'Unable to complete RAG estimate.')
    }
  }, [form])

  return (
    <div className="mx-auto max-w-[96rem] px-4 py-8 text-left text-slate-900 dark:text-slate-100">
      <div className="flex flex-col gap-6 lg:flex-row lg:items-start">
        <SessionHistorySidebar
          sessions={sessionList}
          status={sessionListStatus}
          errorMessage={sessionListError}
          activeSessionId={sessionId}
          disabled={resetInProgress || selectInProgress || sessionStatus !== 'ready'}
          onSelect={(id) => void handleSelectSession(id)}
          onRetry={() => void refreshSessionList()}
        />

        <div className="min-w-0 flex-1">
          <EstimatorHeader
            sessionId={sessionId}
            sessionStatus={sessionStatus}
            sessionError={sessionError}
            resetInProgress={resetInProgress}
            onNewConversation={() => void handleNewConversation()}
            onRetrySession={() => void bootstrapSession()}
            retrievalDebugHref={retrievalDebugHref}
            themeControl={themeControl}
          />

          <div className="mt-6 grid grid-cols-1 gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(320px,400px)]">
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

          <div className="mt-6">
            <EstimateResultPanel
              status={estimateStatus}
              estimate={estimate}
              errorMessage={estimateError}
              warnings={warnings}
              ragResponse={ragResponse}
              ragStatus={ragStatus}
              ragErrorMessage={ragError}
              onRunRagEstimate={() => void handleRunRagEstimate()}
              ragRunDisabled={formDisabled || !form.transcript.trim()}
            />
          </div>
        </div>
      </div>
    </div>
  )
}
