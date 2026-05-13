import { describe, expect, it } from 'vitest'

import { normalizeAppearance, resolveDark } from './appearance'

describe('normalizeAppearance', () => {
  it('returns system for null or unknown', () => {
    expect(normalizeAppearance(null)).toBe('system')
    expect(normalizeAppearance('')).toBe('system')
    expect(normalizeAppearance('auto')).toBe('system')
  })

  it('accepts stored modes', () => {
    expect(normalizeAppearance('light')).toBe('light')
    expect(normalizeAppearance('dark')).toBe('dark')
    expect(normalizeAppearance('system')).toBe('system')
  })
})

describe('resolveDark', () => {
  it('forces dark and light regardless of OS preference', () => {
    expect(resolveDark('dark', false)).toBe(true)
    expect(resolveDark('dark', true)).toBe(true)
    expect(resolveDark('light', false)).toBe(false)
    expect(resolveDark('light', true)).toBe(false)
  })

  it('follows prefers-color-scheme when system', () => {
    expect(resolveDark('system', false)).toBe(false)
    expect(resolveDark('system', true)).toBe(true)
  })
})
