import { useState } from 'react'

import type { PanelStatus } from '../hooks/useSessionEstimate'

type MetadataView = 'readable' | 'memory'

function MetadataSkeleton() {
  return (
    <div className="animate-pulse space-y-3" aria-hidden="true">
      <div className="h-3 w-3/4 rounded bg-slate-700" />
      <div className="h-3 w-full rounded bg-slate-700" />
      <div className="h-3 w-5/6 rounded bg-slate-700" />
    </div>
  )
}

function formatMetadataValue(value: unknown): string {
  if (value === null || value === undefined) {
    return '—'
  }
  if (typeof value === 'string') {
    return value
  }
  if (typeof value === 'number' || typeof value === 'boolean') {
    return String(value)
  }
  if (Array.isArray(value)) {
    return value.map((v) => formatMetadataValue(v)).join(', ')
  }
  return JSON.stringify(value, null, 2)
}

function GroupedMetadata({ data }: { data: Record<string, unknown> }) {
  const sections: { title: string; keys: string[] }[] = [
    { title: 'General', keys: ['project_name', 'project_type', 'target_audience', 'industry', 'summary'] },
    {
      title: 'Context',
      keys: ['detected_constraints', 'attachment_summary'],
    },
    { title: 'Notes', keys: ['confidence_notes'] },
  ]

  return (
    <dl className="space-y-6 text-sm">
      {sections.map(({ title, keys }) => {
        const entries = keys.filter((k) => k in data)
        if (entries.length === 0) {
          return null
        }
        return (
          <div key={title}>
            <dt className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-400">{title}</dt>
            {entries.map((key) => (
              <div key={key} className="mb-3 border-b border-slate-800 pb-2 last:border-0">
                <dd className="font-mono text-[10px] uppercase text-slate-500">{key}</dd>
                <dd className="mt-1 whitespace-pre-wrap text-slate-100">{formatMetadataValue(data[key])}</dd>
              </div>
            ))}
          </div>
        )
      })}
    </dl>
  )
}

function JsonMetadataViewer({ data }: { data: Record<string, unknown> }) {
  const json = JSON.stringify(data, null, 2)
  return (
    <pre
      className="overflow-auto text-xs leading-relaxed text-slate-100"
      aria-label="Project metadata JSON"
    >
      <code>{json}</code>
    </pre>
  )
}

export function ProjectMetadataPanel({
  status,
  metadata,
}: {
  status: PanelStatus
  metadata: Record<string, unknown> | null
}) {
  const [view, setView] = useState<MetadataView>('readable')

  return (
    <section
      className="flex h-full min-h-[280px] flex-col rounded-xl border border-slate-200 bg-white p-5 shadow-sm dark:border-slate-700 dark:bg-slate-900"
      aria-label="Project metadata"
    >
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <h2 className="text-lg font-semibold text-slate-900 dark:text-white">Project metadata</h2>
          <p className="text-xs text-slate-500 dark:text-slate-400">Derived</p>
        </div>
        {status === 'available' && metadata ? (
          <div
            className="inline-flex rounded-lg border border-slate-200 bg-slate-100 p-0.5 dark:border-slate-600 dark:bg-slate-800"
            role="tablist"
            aria-label="Metadata view"
          >
            <button
              type="button"
              role="tab"
              aria-selected={view === 'readable'}
              onClick={() => setView('readable')}
              className={`rounded-md px-2.5 py-1 text-xs font-medium transition-colors ${
                view === 'readable'
                  ? 'bg-white text-slate-900 shadow-sm dark:bg-slate-900 dark:text-white'
                  : 'text-slate-600 hover:text-slate-900 dark:text-slate-400 dark:hover:text-white'
              }`}
            >
              Readable
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={view === 'memory'}
              onClick={() => setView('memory')}
              className={`rounded-md px-2.5 py-1 text-xs font-medium transition-colors ${
                view === 'memory'
                  ? 'bg-teal-600 text-white shadow-sm'
                  : 'text-slate-600 hover:text-slate-900 dark:text-slate-400 dark:hover:text-white'
              }`}
            >
              Memory (current)
            </button>
          </div>
        ) : null}
      </div>
      <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">
        Derived memory for debugging and transparency.
      </p>
      <div className="mt-4 flex-1 overflow-auto rounded-lg bg-slate-950 p-4 text-slate-100" aria-busy={status === 'loading'}>
        {status === 'empty' ? (
          <p className="text-sm text-slate-400">
            Metadata will appear after you generate an estimate.
          </p>
        ) : null}
        {status === 'loading' ? <MetadataSkeleton /> : null}
        {status === 'available' && metadata ? (
          view === 'readable' ? (
            <GroupedMetadata data={metadata} />
          ) : (
            <JsonMetadataViewer data={metadata} />
          )
        ) : null}
      </div>
      <p className="mt-3 text-[11px] text-slate-500 dark:text-slate-500">Auto-generated from inputs</p>
    </section>
  )
}
