import { useState } from 'react'

import type { RagEstimationResponse } from '../api/ragEstimateApi'
import { isRagEstimationResult } from '../api/ragEstimateApi'
import type { PanelStatus } from '../hooks/useSessionEstimate'

import { RagCitationTableView } from './RagCitationTable'
import { StructuredEstimateSummary } from './StructuredEstimateSummary'

function ResultSkeleton() {
  return (
    <div className="animate-pulse space-y-4" aria-hidden="true">
      <div className="h-4 w-1/3 rounded bg-slate-200 dark:bg-slate-700" />
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        {[1, 2, 3, 4].map((n) => (
          <div key={n} className="h-20 rounded bg-slate-200 dark:bg-slate-700" />
        ))}
      </div>
    </div>
  )
}

function EstimateWarnings({ warnings }: { warnings: string[] }) {
  if (warnings.length === 0) {
    return null
  }
  return (
    <div
      className="mb-6 rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900 dark:border-amber-900 dark:bg-amber-950/50 dark:text-amber-100"
      role="status"
      aria-label="Estimate warnings"
    >
      <h3 className="mb-2 text-sm font-semibold text-amber-950 dark:text-amber-50">Warnings</h3>
      <ul className="list-disc space-y-1 pl-5">
        {warnings.map((w) => (
          <li key={w}>{w}</li>
        ))}
      </ul>
    </div>
  )
}

type ResultTab = 'cag' | 'rag'

function ResultTabs({
  active,
  onChange,
  showCag,
  showRag,
}: {
  active: ResultTab
  onChange: (tab: ResultTab) => void
  showCag: boolean
  showRag: boolean
}) {
  if (!showCag || !showRag) {
    return null
  }

  const tabClass = (tab: ResultTab) =>
    `rounded-md px-3 py-1.5 text-sm font-medium ${
      active === tab
        ? 'bg-teal-600 text-white'
        : 'text-slate-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800'
    }`

  return (
    <div className="mb-4 flex gap-2" role="tablist" aria-label="Estimate result views">
      <button type="button" role="tab" className={tabClass('cag')} onClick={() => onChange('cag')}>
        CAG estimate
      </button>
      <button type="button" role="tab" className={tabClass('rag')} onClick={() => onChange('rag')}>
        RAG citations
      </button>
    </div>
  )
}

export function EstimateResultPanel({
  status,
  estimate,
  errorMessage,
  warnings = [],
  ragResponse = null,
  ragStatus = 'empty',
  ragErrorMessage = null,
  onRunRagEstimate,
  ragRunDisabled = false,
}: {
  status: PanelStatus
  estimate: Record<string, unknown> | null
  errorMessage: string | null
  warnings?: string[]
  ragResponse?: RagEstimationResponse | null
  ragStatus?: PanelStatus
  ragErrorMessage?: string | null
  onRunRagEstimate?: () => void
  ragRunDisabled?: boolean
}) {
  const hasCagEstimate = status === 'available' && estimate !== null
  const hasRagEstimate = ragStatus === 'available' && ragResponse !== null
  const estimateIsRagOnly = hasCagEstimate && isRagEstimationResult(estimate)
  const showCagTab = hasCagEstimate && !estimateIsRagOnly
  const showRagTab = hasRagEstimate || estimateIsRagOnly
  const [activeTab, setActiveTab] = useState<ResultTab>(showRagTab && !showCagTab ? 'rag' : 'cag')

  const effectiveTab: ResultTab =
    showCagTab && showRagTab ? activeTab : showRagTab ? 'rag' : 'cag'

  const ragPayload: RagEstimationResponse | null =
    ragResponse ??
    (estimateIsRagOnly
      ? {
          result: estimate as RagEstimationResponse['result'],
          citation_summary: {
            grounded_ok: 0,
            dangling: 0,
            insufficient: 0,
            integrity_violations: 0,
            has_dangling: false,
          },
          request_id: 'embedded',
        }
      : null)

  const panelBusy = status === 'loading' || ragStatus === 'loading'

  return (
    <section
      className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm dark:border-slate-700 dark:bg-slate-900"
      aria-label="Estimate result"
      aria-busy={panelBusy}
    >
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <h2 className="text-lg font-semibold text-slate-900 dark:text-white">Estimate result</h2>
        {onRunRagEstimate ? (
          <button
            type="button"
            disabled={ragRunDisabled || ragStatus === 'loading'}
            onClick={() => onRunRagEstimate()}
            className="rounded border border-violet-300 px-3 py-1.5 text-sm font-medium text-violet-800 hover:bg-violet-50 disabled:opacity-50 dark:border-violet-700 dark:text-violet-200 dark:hover:bg-violet-950"
          >
            {ragStatus === 'loading' ? 'Running RAG…' : 'Run RAG estimate'}
          </button>
        ) : null}
      </div>

      {status === 'empty' && ragStatus === 'empty' ? (
        <p className="mt-4 text-sm text-slate-500 dark:text-slate-400">
          Run Generate estimate or Run RAG estimate to see output here.
        </p>
      ) : null}

      {status === 'loading' ? (
        <div className="mt-4">
          <p className="mb-4 text-sm text-slate-600 dark:text-slate-300">Generating estimate…</p>
          <ResultSkeleton />
        </div>
      ) : null}

      {status === 'error' && errorMessage ? (
        <div role="alert" className="mt-4 rounded-lg border border-red-300 bg-red-50 p-4 text-sm text-red-900 dark:border-red-800 dark:bg-red-950 dark:text-red-100">
          {errorMessage}
        </div>
      ) : null}

      {ragStatus === 'loading' && status !== 'loading' ? (
        <div className="mt-4">
          <p className="mb-4 text-sm text-slate-600 dark:text-slate-300">Running grounded RAG estimate…</p>
          <ResultSkeleton />
        </div>
      ) : null}

      {ragStatus === 'error' && ragErrorMessage ? (
        <div role="alert" className="mt-4 rounded-lg border border-red-300 bg-red-50 p-4 text-sm text-red-900 dark:border-red-800 dark:bg-red-950 dark:text-red-100">
          {ragErrorMessage}
        </div>
      ) : null}

      {(hasCagEstimate || hasRagEstimate || estimateIsRagOnly) && !panelBusy ? (
        <div className="mt-4">
          <EstimateWarnings warnings={warnings} />
          <ResultTabs
            active={effectiveTab}
            onChange={setActiveTab}
            showCag={showCagTab}
            showRag={showRagTab}
          />
          {effectiveTab === 'cag' && showCagTab && estimate ? (
            <StructuredEstimateSummary data={estimate} />
          ) : null}
          {effectiveTab === 'rag' && showRagTab && ragPayload ? (
            <RagCitationTableView response={ragPayload} />
          ) : null}
        </div>
      ) : null}
    </section>
  )
}
