import type { ReactNode } from 'react'

import type { SessionStatus } from '../hooks/useSessionEstimate'

function truncateSessionId(id: string, max = 24): string {
  if (id.length <= max) {
    return id
  }
  return `${id.slice(0, 10)}…${id.slice(-8)}`
}

export function EstimatorHeader({
  sessionId,
  sessionStatus,
  sessionError,
  resetInProgress,
  onNewConversation,
  onRetrySession,
  themeControl,
}: {
  sessionId: string | null
  sessionStatus: SessionStatus
  sessionError: string | null
  resetInProgress: boolean
  onNewConversation: () => void
  onRetrySession: () => void
  themeControl: ReactNode
}) {
  const statusLabel =
    sessionStatus === 'loading'
      ? 'Initializing…'
      : sessionStatus === 'ready'
        ? 'Active'
        : sessionStatus === 'error'
          ? 'Error'
          : '—'

  const formDisabled = sessionStatus !== 'ready' || resetInProgress

  return (
    <header className="mb-6 flex flex-col gap-4 border-b border-slate-200 pb-6 dark:border-slate-800 sm:flex-row sm:items-center sm:justify-between">
      <div className="min-w-0 flex-1">
        <h1 className="text-2xl font-semibold text-slate-900 dark:text-white">Estimator</h1>
        <div className="mt-2 flex flex-wrap items-center gap-2 text-sm text-slate-600 dark:text-slate-400">
          <span className="text-slate-500 dark:text-slate-500">session_id:</span>
          {sessionId ? (
            <code
              className="max-w-full truncate rounded bg-slate-200 px-2 py-0.5 font-mono text-xs text-slate-800 dark:bg-slate-800 dark:text-slate-100"
              title={sessionId}
            >
              {truncateSessionId(sessionId)}
            </code>
          ) : (
            <span className="font-mono text-xs">—</span>
          )}
          <span
            className={`rounded-full px-2 py-0.5 text-xs font-medium ${
              sessionStatus === 'ready'
                ? 'bg-teal-100 text-teal-800 dark:bg-teal-950 dark:text-teal-200'
                : sessionStatus === 'error'
                  ? 'bg-red-100 text-red-800 dark:bg-red-950 dark:text-red-200'
                  : 'bg-slate-200 text-slate-700 dark:bg-slate-800 dark:text-slate-300'
            }`}
          >
            {statusLabel}
          </span>
          {sessionId ? (
            <button
              type="button"
              className="text-xs text-teal-700 underline hover:text-teal-600 dark:text-teal-300"
              onClick={() => void navigator.clipboard.writeText(sessionId)}
            >
              Copy
            </button>
          ) : null}
        </div>
        {sessionError ? (
          <div role="alert" className="mt-3 text-sm text-red-600 dark:text-red-400">
            <p>{sessionError}</p>
            <button
              type="button"
              className="mt-2 rounded border border-red-300 px-3 py-1 text-xs hover:bg-red-50 dark:border-red-800 dark:hover:bg-red-950"
              onClick={() => void onRetrySession()}
            >
              Retry
            </button>
          </div>
        ) : null}
      </div>
      <div className="flex shrink-0 flex-wrap items-center gap-3">
        <button
          type="button"
          disabled={formDisabled}
          onClick={() => void onNewConversation()}
          className="rounded border border-slate-300 px-4 py-2 text-sm font-medium text-slate-800 hover:bg-slate-100 disabled:opacity-50 dark:border-slate-600 dark:text-slate-200 dark:hover:bg-slate-800"
        >
          {resetInProgress ? 'Starting…' : 'New conversation'}
        </button>
        {themeControl}
      </div>
    </header>
  )
}
