import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { EstimatorHeader } from './EstimatorHeader'

function renderHeader(retrievalDebugHref?: string) {
  render(
    <EstimatorHeader
      onNewConversation={vi.fn()}
      onRetrySession={vi.fn()}
      resetInProgress={false}
      retrievalDebugHref={retrievalDebugHref}
      sessionError={null}
      sessionId="session-123"
      sessionStatus="ready"
      themeControl={<span>Theme control</span>}
    />,
  )
}

describe('EstimatorHeader', () => {
  afterEach(() => {
    cleanup()
  })

  it('links to retrieval debug when the internal route is enabled', () => {
    renderHeader('/debug/retrieval')

    const link = screen.getByRole('link', { name: 'Retrieval Debug' })
    expect(link.getAttribute('href')).toBe('/debug/retrieval')
  })

  it('hides the retrieval debug link when no href is provided', () => {
    renderHeader()

    expect(screen.queryByRole('link', { name: 'Retrieval Debug' })).toBeNull()
  })
})
