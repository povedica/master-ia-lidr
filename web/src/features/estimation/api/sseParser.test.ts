import { describe, expect, it } from 'vitest'

import { EstimationSseParser } from './sseParser'

describe('EstimationSseParser', () => {
  it('emits chunk with concatenated content from data lines', () => {
    const p = new EstimationSseParser()
    const out: ReturnType<EstimationSseParser['pushLine']> = []
    out.push(...p.pushLine('event: chunk'))
    out.push(...p.pushLine('data: {"content":"## Hello"}'))
    out.push(...p.pushLine(''))
    expect(out).toEqual([{ kind: 'chunk', text: '## Hello' }])
  })

  it('emits done with parsed JSON object', () => {
    const p = new EstimationSseParser()
    const out: ReturnType<EstimationSseParser['pushLine']> = []
    out.push(...p.pushLine('event: done'))
    out.push(...p.pushLine('data: {"status":"completed","model":"gpt-4o-mini"}'))
    out.push(...p.pushLine(''))
    expect(out).toEqual([
      {
        kind: 'done',
        data: { status: 'completed', model: 'gpt-4o-mini' },
      },
    ])
  })

  it('emits error with message from payload', () => {
    const p = new EstimationSseParser()
    const out: ReturnType<EstimationSseParser['pushLine']> = []
    out.push(...p.pushLine('event: error'))
    out.push(...p.pushLine('data: {"message":"All providers failed."}'))
    out.push(...p.pushLine(''))
    expect(out).toEqual([{ kind: 'error', message: 'All providers failed.' }])
  })

  it('buffers until blank line then emits multiple flushed events in order', () => {
    const p = new EstimationSseParser()
    const acc: ReturnType<EstimationSseParser['pushLine']> = []
    acc.push(...p.pushLine('event: chunk'))
    acc.push(...p.pushLine('data: {"content":"a"}'))
    acc.push(...p.pushLine(''))
    acc.push(...p.pushLine('event: chunk'))
    acc.push(...p.pushLine('data: {"content":"b"}'))
    acc.push(...p.pushLine(''))
    expect(acc).toEqual([
      { kind: 'chunk', text: 'a' },
      { kind: 'chunk', text: 'b' },
    ])
  })

  it('end() flushes a pending event without trailing blank line', () => {
    const p = new EstimationSseParser()
    p.pushLine('event: done')
    p.pushLine('data: {"status":"completed"}')
    expect(p.end()).toEqual([{ kind: 'done', data: { status: 'completed' } }])
  })

  it('uses default message when error payload omits message', () => {
    const p = new EstimationSseParser()
    p.pushLine('event: error')
    p.pushLine('data: {}')
    expect(p.pushLine('')).toEqual([{ kind: 'error', message: 'Streaming failed.' }])
  })
})
