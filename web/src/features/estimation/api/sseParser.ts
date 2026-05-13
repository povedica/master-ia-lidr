export type EstimationStreamEvent =
  | { kind: 'chunk'; text: string }
  | { kind: 'done'; data: Record<string, unknown> }
  | { kind: 'error'; message: string }

/** Incremental SSE parser aligned with FastAPI ``EstimationService.serialize_sse_event`` output. */

export class EstimationSseParser {
  private pendingEvent: string | null = null

  private pendingData: string[] = []

  /** Feed a single line (``\\n``-delimited). Blank line flushes the current event block. */

  pushLine(rawLine: string): EstimationStreamEvent[] {
    const line = rawLine.replace(/\r$/, '').trim()
    if (line === '') {
      return this.flush()
    }
    if (line.startsWith('event:')) {
      this.pendingEvent = line.slice('event:'.length).trim()
      return []
    }
    if (line.startsWith('data:')) {
      this.pendingData.push(line.slice('data:'.length).trim())
      return []
    }
    return []
  }

  /** Flush any incomplete event (end of HTTP body). */

  end(): EstimationStreamEvent[] {
    return this.flush()
  }

  private flush(): EstimationStreamEvent[] {
    if (this.pendingEvent === null) {
      this.pendingData = []
      return []
    }
    const rawPayload = this.pendingData.join('').trim()
    const eventName = this.pendingEvent
    this.pendingEvent = null
    this.pendingData = []
    if (!rawPayload) {
      return []
    }
    let payload: unknown
    try {
      payload = JSON.parse(rawPayload) as unknown
    } catch {
      return [{ kind: 'error', message: 'Streaming payload is malformed.' }]
    }
    if (eventName === 'chunk') {
      const content =
        typeof payload === 'object' && payload !== null && 'content' in payload
          ? String((payload as { content?: unknown }).content ?? '')
          : ''
      return [{ kind: 'chunk', text: content }]
    }
    if (eventName === 'done') {
      const data =
        typeof payload === 'object' && payload !== null && !Array.isArray(payload)
          ? (payload as Record<string, unknown>)
          : {}
      return [{ kind: 'done', data }]
    }
    if (eventName === 'error') {
      const message =
        typeof payload === 'object' && payload !== null && 'message' in payload
          ? String((payload as { message?: unknown }).message ?? '').trim()
          : ''
      return [{ kind: 'error', message: message || 'Streaming failed.' }]
    }
    return []
  }
}

/** Split an SSE byte chunk into lines, keeping an incomplete trailing fragment. */

export function splitSseLines(
  buffer: string,
  incoming: string,
): { lines: string[]; rest: string } {
  const combined = buffer + incoming
  const parts = combined.split('\n')
  const rest = parts.pop() ?? ''
  return { lines: parts, rest }
}
