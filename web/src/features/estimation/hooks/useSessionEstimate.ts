import { useCallback, useEffect, useState } from 'react'

import {
  createSession,
  estimateInSession,
  SessionApiError,
  type SessionEstimateResponse,
} from '../api/sessionApi'
import { extractEstimateResult } from '../lib/extractEstimateResult'
import { parseSessionEstimateFailure } from '../lib/sessionValidationErrors'

export type SessionStatus = 'idle' | 'loading' | 'ready' | 'error'
export type PanelStatus = 'empty' | 'loading' | 'available' | 'error'

export type SubmitOutcome =
  | { ok: true; data: SessionEstimateResponse }
  | { ok: false; kind: 'validation'; fieldErrors: Record<string, string>; formSummary?: string }
  | { ok: false; kind: 'generic'; message: string }

const SESSION_BOOTSTRAP_ERROR =
  'Could not start a session. Check that the API is running and try again.'

export function useSessionEstimate() {
  const [sessionId, setSessionId] = useState<string | null>(null)
  const [sessionStatus, setSessionStatus] = useState<SessionStatus>('idle')
  const [sessionError, setSessionError] = useState<string | null>(null)
  const [resetInProgress, setResetInProgress] = useState(false)

  const [projectMetadata, setProjectMetadata] = useState<Record<string, unknown> | null>(null)
  const [metadataStatus, setMetadataStatus] = useState<PanelStatus>('empty')

  const [estimate, setEstimate] = useState<Record<string, unknown> | null>(null)
  const [estimateStatus, setEstimateStatus] = useState<PanelStatus>('empty')
  const [estimateError, setEstimateError] = useState<string | null>(null)
  const [warnings, setWarnings] = useState<string[]>([])

  const clearPanels = useCallback(() => {
    setProjectMetadata(null)
    setMetadataStatus('empty')
    setEstimate(null)
    setEstimateStatus('empty')
    setEstimateError(null)
    setWarnings([])
  }, [])

  const bootstrapSession = useCallback(async () => {
    setSessionStatus('loading')
    setSessionError(null)
    try {
      const { session_id } = await createSession()
      setSessionId(session_id)
      setSessionStatus('ready')
    } catch {
      setSessionId(null)
      setSessionStatus('error')
      setSessionError(SESSION_BOOTSTRAP_ERROR)
    }
  }, [])

  useEffect(() => {
    let active = true
    ;(async () => {
      setSessionStatus('loading')
      setSessionError(null)
      try {
        const { session_id } = await createSession()
        if (!active) {
          return
        }
        setSessionId(session_id)
        setSessionStatus('ready')
      } catch {
        if (!active) {
          return
        }
        setSessionId(null)
        setSessionStatus('error')
        setSessionError(SESSION_BOOTSTRAP_ERROR)
      }
    })()
    return () => {
      active = false
    }
  }, [])

  const resetConversation = useCallback(async () => {
    setResetInProgress(true)
    clearPanels()
    setSessionStatus('loading')
    setSessionError(null)
    try {
      const { session_id } = await createSession()
      setSessionId(session_id)
      setSessionStatus('ready')
    } catch {
      setSessionId(null)
      setSessionStatus('error')
      setSessionError(SESSION_BOOTSTRAP_ERROR)
    } finally {
      setResetInProgress(false)
    }
  }, [clearPanels])

  const submitEstimate = useCallback(
    async (body: Record<string, unknown>): Promise<SubmitOutcome> => {
      if (!sessionId) {
        return { ok: false, kind: 'generic', message: 'Session is not ready.' }
      }
      setEstimateStatus('loading')
      setMetadataStatus('loading')
      setEstimateError(null)
      try {
        const data = await estimateInSession(sessionId, body)
        setProjectMetadata(data.project_metadata)
        setMetadataStatus('available')
        setEstimate(extractEstimateResult(data.estimate))
        setEstimateStatus('available')
        setWarnings(data.warnings ?? [])
        return { ok: true, data }
      } catch (exc) {
        setMetadataStatus(projectMetadata ? 'available' : 'empty')
        setEstimateStatus('error')
        if (exc instanceof SessionApiError) {
          if (exc.status === 422) {
            const parsed = parseSessionEstimateFailure(422, exc.bodyText)
            if (parsed.kind === 'validation') {
              return {
                ok: false,
                kind: 'validation',
                fieldErrors: parsed.fieldErrors,
                formSummary: parsed.formSummary,
              }
            }
            setEstimateError(parsed.message)
            return { ok: false, kind: 'generic', message: parsed.message }
          }
          if (exc.status === 404) {
            const msg = 'This session expired. Start a new conversation.'
            setEstimateError(msg)
            return { ok: false, kind: 'generic', message: msg }
          }
          const msg =
            exc.status >= 500
              ? 'The server is temporarily unavailable. Please try again later.'
              : 'The request could not be completed. Please try again.'
          setEstimateError(msg)
          return { ok: false, kind: 'generic', message: msg }
        }
        const msg = exc instanceof Error ? exc.message : 'The request failed.'
        setEstimateError(msg)
        return { ok: false, kind: 'generic', message: msg }
      }
    },
    [sessionId, projectMetadata],
  )

  return {
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
  }
}
