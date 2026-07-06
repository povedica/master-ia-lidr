import { useState } from 'react'

import type { RagEstimationResult } from '../api/ragEstimateApi'

import { RagCitationSummary } from './RagCitationSummary'

const TABLE_CLASS =
  'min-w-full border-collapse text-left text-xs'

function GroundedBadge({ grounded }: { grounded: boolean }) {
  return (
    <span
      className={`inline-flex rounded-full px-2 py-0.5 text-[11px] font-medium ${
        grounded
          ? 'bg-teal-100 text-teal-900 dark:bg-teal-950 dark:text-teal-100'
          : 'bg-slate-200 text-slate-700 dark:bg-slate-800 dark:text-slate-300'
      }`}
    >
      {grounded ? 'yes' : 'no'}
    </span>
  )
}

function RationaleCell({ rationale }: { rationale: string }) {
  const [expanded, setExpanded] = useState(false)
  const truncated = rationale.length > 120 && !expanded
  const display = truncated ? `${rationale.slice(0, 120)}…` : rationale

  return (
    <div className="max-w-md text-slate-700 dark:text-slate-300">
      <p className="whitespace-pre-wrap">{display}</p>
      {rationale.length > 120 ? (
        <button
          type="button"
          className="mt-1 text-[11px] text-teal-700 underline hover:text-teal-600 dark:text-teal-300"
          onClick={() => setExpanded((value) => !value)}
        >
          {expanded ? 'Show less' : 'Show more'}
        </button>
      ) : null}
    </div>
  )
}

function SourcesList({
  sources,
}: {
  sources: RagEstimationResult['line_items'][number]['sources']
}) {
  if (sources.length === 0) {
    return <span className="text-slate-400">—</span>
  }

  return (
    <ul className="space-y-2">
      {sources.map((source) => (
        <li
          key={`${source.chunk_id}-${source.document_id}`}
          className="rounded border border-slate-200 bg-white px-2 py-1.5 dark:border-slate-700 dark:bg-slate-950"
        >
          <div className="font-mono text-[11px] text-slate-600 dark:text-slate-400">
            chunk {source.chunk_id} · doc {source.document_id}
            {source.budget_id ? ` · ${source.budget_id}` : ''}
          </div>
          <p className="mt-1 text-[11px] leading-relaxed text-slate-700 dark:text-slate-300">
            {source.evidence}
          </p>
        </li>
      ))}
    </ul>
  )
}

export function RagCitationTableView({
  response,
}: {
  response: {
    result: RagEstimationResult
    citation_summary: Parameters<typeof RagCitationSummary>[0]['summary']
  }
}) {
  const { result, citation_summary: citationSummary } = response

  if (result.insufficient_context) {
    return (
      <div className="space-y-4">
        <RagCitationSummary summary={citationSummary} />
        <p className="rounded-lg border border-slate-200 bg-slate-50 px-4 py-6 text-sm text-slate-600 dark:border-slate-700 dark:bg-slate-900/60 dark:text-slate-300">
          Insufficient retrieval context — no grounded line items were produced.
        </p>
      </div>
    )
  }

  return (
    <div className="space-y-4">
      <div>
        <h3 className="text-lg font-semibold tracking-tight text-slate-900 dark:text-white">
          Grounded RAG estimate
        </h3>
        <p className="mt-2 max-w-prose text-sm leading-relaxed text-slate-600 dark:text-slate-300">
          {result.summary}
        </p>
        <p className="mt-2 text-sm text-slate-500 dark:text-slate-400">
          Total: <span className="font-semibold tabular-nums text-slate-800 dark:text-slate-200">{result.total_hours}</span>{' '}
          hours ({result.currency})
        </p>
      </div>

      <RagCitationSummary summary={citationSummary} />

      {result.line_items.length > 0 ? (
        <div className="overflow-x-auto rounded-md border border-slate-200 bg-white dark:border-slate-600 dark:bg-slate-950">
          <table className={TABLE_CLASS}>
            <thead className="bg-slate-100 dark:bg-slate-900">
              <tr>
                <th className="border-b border-slate-200 px-3 py-2 font-medium text-slate-600 dark:border-slate-700 dark:text-slate-300">
                  Component
                </th>
                <th className="border-b border-slate-200 px-3 py-2 font-medium text-slate-600 dark:border-slate-700 dark:text-slate-300">
                  Hours
                </th>
                <th className="border-b border-slate-200 px-3 py-2 font-medium text-slate-600 dark:border-slate-700 dark:text-slate-300">
                  Grounded
                </th>
                <th className="border-b border-slate-200 px-3 py-2 font-medium text-slate-600 dark:border-slate-700 dark:text-slate-300">
                  Rationale
                </th>
                <th className="border-b border-slate-200 px-3 py-2 font-medium text-slate-600 dark:border-slate-700 dark:text-slate-300">
                  Sources
                </th>
              </tr>
            </thead>
            <tbody>
              {result.line_items.map((line, index) => (
                <tr
                  key={`${line.component}-${index}`}
                  className="odd:bg-white even:bg-slate-50 dark:odd:bg-slate-950 dark:even:bg-slate-900/50"
                >
                  <td className="border-b border-slate-100 px-3 py-2 align-top text-slate-800 dark:border-slate-800 dark:text-slate-200">
                    {line.component}
                  </td>
                  <td className="border-b border-slate-100 px-3 py-2 align-top tabular-nums text-slate-800 dark:border-slate-800 dark:text-slate-200">
                    {line.hours}
                  </td>
                  <td className="border-b border-slate-100 px-3 py-2 align-top dark:border-slate-800">
                    <GroundedBadge grounded={line.grounded} />
                  </td>
                  <td className="border-b border-slate-100 px-3 py-2 align-top dark:border-slate-800">
                    <RationaleCell rationale={line.rationale} />
                  </td>
                  <td className="border-b border-slate-100 px-3 py-2 align-top dark:border-slate-800">
                    <SourcesList sources={line.sources} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
    </div>
  )
}
