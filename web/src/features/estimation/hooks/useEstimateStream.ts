import { useCallback, useRef, useState } from 'react'

import { estimateStructuredUrl } from '../api/estimateApi'

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
    async (body: Record<string, unknown>) => {
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
          setError(formatHttpError(response.status, text))
          return
        }

        let data: Record<string, unknown>
        try {
          data = JSON.parse(text) as Record<string, unknown>
        } catch {
          setError('Invalid JSON response from server.')
          return
        }

        setDoneMeta(data)
        const r = data['result']
        if (r && typeof r === 'object' && !Array.isArray(r)) {
          setStructuredResult(r as Record<string, unknown>)
        }
      } catch (exc) {
        if (exc instanceof DOMException && exc.name === 'AbortError') {
          return
        }
        const message = exc instanceof Error ? exc.message : 'Request failed.'
        setError(message)
      } finally {
        setLoading(false)
        aborter.current = null
      }
    },
    [reset],
  )

  return { markdown, structuredResult, loading, error, doneMeta, run, cancel, reset }
}

function formatHttpError(status: number, body: string): string {
  const trimmed = body.trim()
  if (!trimmed) {
    return `HTTP ${status}`
  }
  try {
    const parsed = JSON.parse(trimmed) as { detail?: unknown }
    if (parsed.detail !== undefined) {
      return `HTTP ${status}: ${stringifyDetail(parsed.detail)}`
    }
  } catch {
    /* fall through */
  }
  return `HTTP ${status}: ${trimmed.slice(0, 800)}`
}

function stringifyDetail(detail: unknown): string {
  if (typeof detail === 'string') {
    return detail
  }
  if (Array.isArray(detail)) {
    return detail
      .map((item) => {
        if (item && typeof item === 'object' && 'msg' in item) {
          return String((item as { msg?: unknown }).msg ?? JSON.stringify(item))
        }
        return JSON.stringify(item)
      })
      .join('; ')
  }
  return JSON.stringify(detail)
}
