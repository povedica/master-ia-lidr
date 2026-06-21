import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import App from './App'
import { shouldShowRetrievalDebugPage } from './appRouting'

function stubMatchMedia(): void {
  Object.defineProperty(window, 'matchMedia', {
    writable: true,
    value: vi.fn().mockImplementation((query: string) => ({
      matches: false,
      media: query,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    })),
  })
}

describe('App retrieval debug routing', () => {
  afterEach(() => {
    cleanup()
    vi.unstubAllEnvs()
    window.history.pushState({}, '', '/')
  })

  it('selects the retrieval debug page only for the gated internal route', () => {
    expect(shouldShowRetrievalDebugPage('/debug/retrieval', true)).toBe(true)
    expect(shouldShowRetrievalDebugPage('/debug/retrieval', false)).toBe(false)
    expect(shouldShowRetrievalDebugPage('/', true)).toBe(false)
  })

  it('renders the retrieval debug page when the route and env flag are enabled', () => {
    stubMatchMedia()
    vi.stubEnv('VITE_ENABLE_RETRIEVAL_DEBUG', 'true')
    window.history.pushState({}, '', '/debug/retrieval')

    render(<App />)

    expect(screen.getByText('Retrieval Debug')).toBeTruthy()
  })
})
