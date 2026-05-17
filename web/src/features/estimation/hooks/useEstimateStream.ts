import { useCallback, useRef, useState } from 'react'

import { estimateStructuredUrl } from '../api/estimateApi'
import { parseStructuredEstimateFailure } from '../lib/validationErrors'

export type EstimateRunResult =
  | { ok: true }
  | { ok: false; kind: 'validation'; fieldErrors: Record<string, string>; formSummary?: string }
  | { ok: false; kind: 'generic' }

export function useEstimateStream() {
  const [markdown, setMarkdown] = useState('')
  const [structuredResult, setStructuredResult] = useState<Record<string, unknown> | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [doneMeta, setDoneMeta] = useState<Record<string, unknown> | null>(null)
  const aborter = useRef<AbortController | null>(null)

  const reset = useCallback(() => {
    setMarkdown('')
    setStructuredResult(null)
    setError(null)
    setDoneMeta(null)
  }, [])

  const cancel = useCallback(() => {
    aborter.current?.abort()
  }, [])

  const run = useCallback(
    async (body: Record<string, unknown>): Promise<EstimateRunResult | undefined> => {
      reset()
      setLoading(true)
      const ctrl = new AbortController()
      aborter.current = ctrl
      try {
        const response = await fetch(estimateStructuredUrl(), {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            Accept: 'application/json',
          },
          body: JSON.stringify(body),
          signal: ctrl.signal,
        })

        const text = await response.text().catch(() => '')

        if (!response.ok) {
          if (response.status === 422) {
            const parsed = parseStructuredEstimateFailure(422, text)
            if (parsed.kind === 'validation') {
              setError(null)
              return {
                ok: false,
                kind: 'validation',
                fieldErrors: parsed.fieldErrors,
                formSummary: parsed.formSummary,
              }
            }
            setError(parsed.message)
            return { ok: false, kind: 'generic' }
          }
          const safeMessage =
            response.status >= 500
              ? 'The server is temporarily unavailable. Please try again later.'
              : 'The request could not be completed. Please try again.'
          setError(safeMessage)
          return { ok: false, kind: 'generic' }
        }

        let data: Record<string, unknown>
        try {
          data = JSON.parse(text) as Record<string, unknown>
        } catch {
          setError('Invalid JSON response from server.')
          return { ok: false, kind: 'generic' }
        }

        setDoneMeta(data)
        const r = data['result']
        if (r && typeof r === 'object' && !Array.isArray(r)) {
          setStructuredResult(r as Record<string, unknown>)
        }
        return { ok: true }
      } catch (exc) {
        if (exc instanceof DOMException && exc.name === 'AbortError') {
          return undefined
        }
        const message = exc instanceof Error ? exc.message : 'The request failed.'
        setError(message)
        return { ok: false, kind: 'generic' }
      } finally {
        setLoading(false)
        aborter.current = null
      }
    },
    [reset],
  )

  return { markdown, structuredResult, loading, error, doneMeta, run, cancel, reset }
}
