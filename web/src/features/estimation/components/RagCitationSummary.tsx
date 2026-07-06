import type { CitationSummary } from '../api/ragEstimateApi'

function CountChip({
  label,
  count,
  tone,
}: {
  label: string
  count: number
  tone: 'neutral' | 'ok' | 'warn' | 'danger'
}) {
  const toneClass =
    tone === 'ok'
      ? 'bg-teal-100 text-teal-900 dark:bg-teal-950 dark:text-teal-100'
      : tone === 'warn'
        ? 'bg-amber-100 text-amber-900 dark:bg-amber-950 dark:text-amber-100'
        : tone === 'danger'
          ? 'bg-red-100 text-red-900 dark:bg-red-950 dark:text-red-100'
          : 'bg-slate-100 text-slate-800 dark:bg-slate-800 dark:text-slate-200'

  return (
    <span className={`inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-xs font-medium ${toneClass}`}>
      <span>{label}</span>
      <span className="tabular-nums">{count}</span>
    </span>
  )
}

export function RagCitationSummary({ summary }: { summary: CitationSummary }) {
  return (
    <div
      className={`rounded-lg border px-4 py-3 ${
        summary.has_dangling
          ? 'border-amber-300 bg-amber-50 dark:border-amber-800 dark:bg-amber-950/40'
          : 'border-slate-200 bg-slate-50 dark:border-slate-700 dark:bg-slate-900/60'
      }`}
      role="status"
      aria-label="Citation audit summary"
    >
      <h4 className="text-sm font-semibold text-slate-900 dark:text-white">Citation audit</h4>
      <div className="mt-2 flex flex-wrap gap-2">
        <CountChip label="Grounded OK" count={summary.grounded_ok} tone="ok" />
        <CountChip label="Dangling" count={summary.dangling} tone={summary.has_dangling ? 'danger' : 'neutral'} />
        <CountChip label="Insufficient" count={summary.insufficient} tone="warn" />
        <CountChip label="Integrity" count={summary.integrity_violations} tone="danger" />
      </div>
      {summary.has_dangling ? (
        <p className="mt-2 text-xs text-amber-900 dark:text-amber-100">
          One or more lines cite chunks that were not in the retrieved context.
        </p>
      ) : null}
    </div>
  )
}
