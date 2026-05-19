import { useState } from 'react'

import type { SessionListItem } from '../api/sessionApi'
import type { SessionListStatus } from '../hooks/useSessionEstimate'

function HistoryIcon({ className }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 20 20" fill="none" aria-hidden="true">
      <path
        d="M10 4.5a5.5 5.5 0 1 0 5.5 5.5"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinecap="round"
      />
      <path d="M10 7v3.2l2.2 1.3" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
      <path d="M6.5 4.5H10V2" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
    </svg>
  )
}

function CurrentIcon({ className }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 20 20" fill="none" aria-hidden="true">
      <path
        d="M5 4.5h10M5 8h10M5 11.5h6"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinecap="round"
      />
      <path
        d="M13.5 10.5 15 12l-2.5 2.5"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  )
}

function displayLabel(item: SessionListItem, activeSessionId: string | null): string {
  if (item.session_id === activeSessionId && item.submit_count === 0) {
    return 'Current estimation'
  }
  return item.label
}

export function SessionHistorySidebar({
  sessions,
  status,
  errorMessage,
  activeSessionId,
  disabled,
  onSelect,
  onRetry,
}: {
  sessions: SessionListItem[]
  status: SessionListStatus
  errorMessage: string | null
  activeSessionId: string | null
  disabled: boolean
  onSelect: (sessionId: string) => void
  onRetry: () => void
}) {
  const [collapsed, setCollapsed] = useState(false)

  return (
    <aside
      className={`flex shrink-0 flex-col rounded-xl border border-slate-200 bg-slate-100/80 transition-[width] duration-200 dark:border-slate-700 dark:bg-slate-900/60 ${
        collapsed ? 'w-12' : 'w-64 lg:w-72'
      }`}
      aria-label="Sessions project history"
    >
      <SidebarHeader collapsed={collapsed} onToggle={() => setCollapsed((v) => !v)} />

      {!collapsed ? (
        <SidebarBody
          sessions={sessions}
          status={status}
          errorMessage={errorMessage}
          activeSessionId={activeSessionId}
          disabled={disabled}
          onSelect={onSelect}
          onRetry={onRetry}
        />
      ) : null}
    </aside>
  )
}

function SidebarHeader({
  collapsed,
  onToggle,
}: {
  collapsed: boolean
  onToggle: () => void
}) {
  return (
    <div className="flex items-start justify-between gap-2 border-b border-slate-200/80 p-3 dark:border-slate-700">
      {!collapsed ? (
        <div className="min-w-0 flex-1">
          <h2 className="text-sm font-bold text-teal-800 dark:text-teal-300">Sessions project history</h2>
          <p className="text-xs text-slate-500 dark:text-slate-400">Last 30 days</p>
        </div>
      ) : (
        <span className="sr-only">Sessions project history</span>
      )}
      <button
        type="button"
        onClick={onToggle}
        className="rounded-md p-1.5 text-slate-600 hover:bg-slate-200 dark:text-slate-300 dark:hover:bg-slate-800"
        aria-expanded={!collapsed}
        aria-label={collapsed ? 'Expand session history' : 'Collapse session history'}
      >
        <span className="flex items-center gap-0.5 text-xs font-medium">
          <span className="flex flex-col gap-0.5">
            <span className="block h-0.5 w-3 rounded bg-current" />
            <span className="block h-0.5 w-3 rounded bg-current" />
            <span className="block h-0.5 w-3 rounded bg-current" />
          </span>
          <span aria-hidden className="ml-0.5">
            {collapsed ? '›' : '‹'}
          </span>
        </span>
      </button>
    </div>
  )
}

function SidebarBody({
  sessions,
  status,
  errorMessage,
  activeSessionId,
  disabled,
  onSelect,
  onRetry,
}: {
  sessions: SessionListItem[]
  status: SessionListStatus
  errorMessage: string | null
  activeSessionId: string | null
  disabled: boolean
  onSelect: (sessionId: string) => void
  onRetry: () => void
}) {
  if (status === 'loading') {
    return (
      <ul className="space-y-2 p-3" aria-busy="true">
        {[0, 1, 2].map((i) => (
          <li key={i} className="h-9 animate-pulse rounded-lg bg-slate-200 dark:bg-slate-800" />
        ))}
      </ul>
    )
  }

  if (status === 'error') {
    return (
      <div className="p-3 text-sm">
        <p className="text-red-600 dark:text-red-400" role="alert">
          {errorMessage ?? 'Could not load sessions.'}
        </p>
        <button
          type="button"
          onClick={onRetry}
          className="mt-2 text-sm font-medium text-teal-700 underline dark:text-teal-400"
        >
          Retry
        </button>
      </div>
    )
  }

  return (
    <ul className="space-y-1 p-2">
      {sessions.length === 0 ? (
        <li className="px-3 py-2 text-sm text-slate-500">No sessions yet.</li>
      ) : (
        sessions.map((item) => {
          const active = item.session_id === activeSessionId
          const isCurrent = active && item.submit_count === 0
          return (
            <li key={item.session_id}>
              <button
                type="button"
                disabled={disabled || active}
                onClick={() => onSelect(item.session_id)}
                className={`flex w-full items-center gap-2 rounded-lg px-3 py-2.5 text-left text-sm transition-colors ${
                  active
                    ? 'bg-teal-600 font-medium text-white shadow-sm'
                    : 'text-slate-700 hover:bg-slate-200/80 dark:text-slate-200 dark:hover:bg-slate-800'
                } disabled:cursor-default`}
                aria-current={active ? 'true' : undefined}
              >
                {isCurrent ? (
                  <CurrentIcon className="h-4 w-4 shrink-0" />
                ) : (
                  <HistoryIcon className={`h-4 w-4 shrink-0 ${active ? '' : 'opacity-70'}`} />
                )}
                <span className="truncate">{displayLabel(item, activeSessionId)}</span>
              </button>
            </li>
          )
        })
      )}
    </ul>
  )
}
