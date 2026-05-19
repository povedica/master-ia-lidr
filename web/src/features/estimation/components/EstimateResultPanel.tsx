import type { PanelStatus } from '../hooks/useSessionEstimate'

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

export function EstimateResultPanel({
  status,
  estimate,
  errorMessage,
}: {
  status: PanelStatus
  estimate: Record<string, unknown> | null
  errorMessage: string | null
}) {
  return (
    <section
      className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm dark:border-slate-700 dark:bg-slate-900"
      aria-label="Estimate result"
      aria-busy={status === 'loading'}
    >
      <h2 className="text-lg font-semibold text-slate-900 dark:text-white">Estimate result</h2>
      {status === 'empty' ? (
        <p className="mt-4 text-sm text-slate-500 dark:text-slate-400">
          Run Generate estimate to see the output here.
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
      {status === 'available' && estimate ? (
        <div className="mt-4">
          <StructuredEstimateSummary data={estimate} />
        </div>
      ) : null}
    </section>
  )
}
