import { useCallback, useRef, useState } from 'react'

import { estimateStreamUrl } from '../api/estimateApi'
import { EstimationSseParser } from '../api/sseParser'

export function useEstimateStream() {
  const [markdown, setMarkdown] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [doneMeta, setDoneMeta] = useState<Record<string, unknown> | null>(null)
  const aborter = useRef<AbortController | null>(null)

  const reset = useCallback(() => {
    setMarkdown('')
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
      const parser = new EstimationSseParser()
      let lineBuffer = ''
      try {
        const response = await fetch(estimateStreamUrl(), {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            Accept: 'text/event-stream',
          },
          body: JSON.stringify(body),
          signal: ctrl.signal,
        })

        if (!response.ok) {
          const text = await response.text().catch(() => '')
          setError(formatHttpError(response.status, text))
          return
        }

        if (!response.body) {
          setError('Empty response body.')
          return
        }

        const reader = response.body.getReader()
        const decoder = new TextDecoder()
        while (true) {
          const { done, value } = await reader.read()
          if (done) {
            break
          }
          lineBuffer += decoder.decode(value, { stream: true })
          let newlineIndex: number
          while ((newlineIndex = lineBuffer.indexOf('\n')) >= 0) {
            const line = lineBuffer.slice(0, newlineIndex)
            lineBuffer = lineBuffer.slice(newlineIndex + 1)
            for (const event of parser.pushLine(line)) {
              if (event.kind === 'chunk') {
                setMarkdown((prev) => prev + event.text)
              } else if (event.kind === 'done') {
                setDoneMeta(event.data)
              } else if (event.kind === 'error') {
                setError(event.message)
              }
            }
          }
        }

        for (const event of parser.end()) {
          if (event.kind === 'chunk') {
            setMarkdown((prev) => prev + event.text)
          } else if (event.kind === 'done') {
            setDoneMeta(event.data)
          } else if (event.kind === 'error') {
            setError(event.message)
          }
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

  return { markdown, loading, error, doneMeta, run, cancel, reset }
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
