import { type FormEvent, type ReactNode, useState } from 'react'

import {
  RetrievalDebugApiError,
  retrievalStrategySchema,
  runRetrievalDebug,
  type RetrievalDebugRequest,
  type RetrievalDebugResponse,
} from '../api/retrievalDebugApi'

type RetrievalDebugStatus = 'idle' | 'loading' | 'results' | 'empty' | 'error'
type RetrievalStrategy = RetrievalDebugRequest['strategies'][number]

const RECENT_SEARCHES_KEY = 'retrieval-debug-recent-searches'

type TuningState = {
  vectorTopK: string
  semanticThreshold: string
  lexicalTopK: string
  maxResults: string
  hybridEnabled: boolean
  hybridMethod: 'rrf' | 'weighted'
  rrfK: string
  vectorWeight: string
  lexicalWeight: string
  rerankEnabled: boolean
  clientSector: string
  tags: string
  yearFrom: string
  yearTo: string
}

type RecentSearch = {
  query: string
  strategy: RetrievalStrategy
  tuning: TuningState
}

type RetrievalDebugPageProps = {
  runDebug?: (request: RetrievalDebugRequest) => Promise<RetrievalDebugResponse>
  themeControl?: ReactNode
}

const initialTuning: TuningState = {
  vectorTopK: '10',
  semanticThreshold: '',
  lexicalTopK: '10',
  maxResults: '10',
  hybridEnabled: true,
  hybridMethod: 'rrf',
  rrfK: '60',
  vectorWeight: '0.5',
  lexicalWeight: '0.5',
  rerankEnabled: false,
  clientSector: '',
  tags: '',
  yearFrom: '',
  yearTo: '',
}

function friendlyErrorMessage(error: unknown): string {
  if (error instanceof RetrievalDebugApiError && error.status === 503) {
    return 'Retrieval debug is temporarily unavailable.'
  }
  if (error instanceof RetrievalDebugApiError && error.status === 422) {
    return 'The retrieval debug request is invalid. Check the query and controls.'
  }
  return 'Unable to complete retrieval debug.'
}

function parseOptionalNumber(value: string): number | undefined {
  const trimmed = value.trim()
  if (!trimmed) {
    return undefined
  }
  const parsed = Number(trimmed)
  return Number.isFinite(parsed) ? parsed : undefined
}

function parseOptionalInteger(value: string): number | undefined {
  const parsed = parseOptionalNumber(value)
  return parsed === undefined ? undefined : Math.trunc(parsed)
}

function buildRetrievalDebugRequest(
  query: string,
  strategy: RetrievalStrategy,
  tuning: TuningState,
): RetrievalDebugRequest {
  const tags = tuning.tags
    .split(',')
    .map((tag) => tag.trim())
    .filter(Boolean)
  const yearFrom = parseOptionalInteger(tuning.yearFrom)
  const yearTo = parseOptionalInteger(tuning.yearTo)
  const filters: NonNullable<RetrievalDebugRequest['filters']> = {}
  if (tuning.clientSector.trim()) {
    filters.client_sector = tuning.clientSector.trim()
  }
  if (tags.length > 0) {
    filters.tags = tags
  }
  if (yearFrom !== undefined || yearTo !== undefined) {
    filters.year = {
      ...(yearFrom !== undefined ? { from: yearFrom } : {}),
      ...(yearTo !== undefined ? { to: yearTo } : {}),
    }
  }

  const hybrid: NonNullable<RetrievalDebugRequest['hybrid']> = {
    enabled: tuning.hybridEnabled,
    method: tuning.hybridMethod,
    rrf_k: parseOptionalInteger(tuning.rrfK) ?? 60,
  }
  if (tuning.hybridMethod === 'weighted') {
    hybrid.weights = {
      vector: parseOptionalNumber(tuning.vectorWeight) ?? 0.5,
      lexical: parseOptionalNumber(tuning.lexicalWeight) ?? 0.5,
    }
  }

  return {
    query,
    strategies: [strategy],
    vector: {
      top_k: parseOptionalInteger(tuning.vectorTopK) ?? 10,
      threshold: parseOptionalNumber(tuning.semanticThreshold) ?? null,
    },
    lexical: {
      top_k: parseOptionalInteger(tuning.lexicalTopK) ?? 10,
    },
    hybrid,
    rerank: { enabled: tuning.rerankEnabled },
    ...(Object.keys(filters).length > 0 ? { filters } : {}),
    max_results: parseOptionalInteger(tuning.maxResults) ?? 10,
  }
}

function loadRecentSearches(): RecentSearch[] {
  try {
    const raw = localStorage.getItem(RECENT_SEARCHES_KEY)
    if (!raw) {
      return []
    }
    const parsed = JSON.parse(raw) as RecentSearch[]
    return parsed.filter((item) => retrievalStrategySchema.safeParse(item.strategy).success)
  } catch {
    return []
  }
}

function saveRecentSearch(search: RecentSearch): RecentSearch[] {
  const next = [
    search,
    ...loadRecentSearches().filter(
      (item) => item.query !== search.query || item.strategy !== search.strategy,
    ),
  ].slice(0, 5)
  localStorage.setItem(RECENT_SEARCHES_KEY, JSON.stringify(next))
  return next
}

export function RetrievalDebugPage({
  runDebug = runRetrievalDebug,
  themeControl,
}: RetrievalDebugPageProps) {
  const [query, setQuery] = useState('')
  const [strategy, setStrategy] = useState<RetrievalStrategy>('all')
  const [tuning, setTuning] = useState<TuningState>(initialTuning)
  const [recentSearches, setRecentSearches] = useState<RecentSearch[]>(loadRecentSearches)
  const [status, setStatus] = useState<RetrievalDebugStatus>('idle')
  const [response, setResponse] = useState<RetrievalDebugResponse | null>(null)
  const [errorMessage, setErrorMessage] = useState<string | null>(null)

  async function onSubmit(ev: FormEvent) {
    ev.preventDefault()
    const trimmedQuery = query.trim()
    if (!trimmedQuery || status === 'loading') {
      return
    }
    setStatus('loading')
    setErrorMessage(null)
    setResponse(null)
    try {
      const request = buildRetrievalDebugRequest(trimmedQuery, strategy, tuning)
      const nextResponse = await runDebug(request)
      setRecentSearches(saveRecentSearch({ query: trimmedQuery, strategy, tuning }))
      setResponse(nextResponse)
      setStatus(nextResponse.final_results.length > 0 ? 'results' : 'empty')
    } catch (error) {
      setErrorMessage(friendlyErrorMessage(error))
      setStatus('error')
    }
  }

  return (
    <main className="mx-auto max-w-7xl px-4 py-8 text-left text-slate-900 dark:text-slate-100">
      <header className="mb-6 flex flex-col gap-4 border-b border-slate-200 pb-6 dark:border-slate-800 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <p className="text-sm font-medium uppercase tracking-wide text-violet-600 dark:text-violet-300">
            Internal tooling
          </p>
          <h1 className="mt-2 text-3xl font-semibold">Retrieval Debug</h1>
          <p className="mt-2 max-w-3xl text-sm text-slate-600 dark:text-slate-400">
            Compare retrieval branches, ranking changes, and explanations for a single query.
          </p>
        </div>
        {themeControl}
      </header>

      <form
        className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm dark:border-slate-800 dark:bg-slate-900"
        onSubmit={onSubmit}
      >
        <QueryBox
          disabled={status === 'loading'}
          onQueryChange={setQuery}
          onRecentSearch={(search) => {
            setQuery(search.query)
            setStrategy(search.strategy)
            setTuning(search.tuning)
          }}
          onStrategyChange={setStrategy}
          query={query}
          recentSearches={recentSearches}
          strategy={strategy}
        />
        <TuningPanel
          disabled={status === 'loading'}
          onChange={(patch) => setTuning((current) => ({ ...current, ...patch }))}
          tuning={tuning}
        />
        <div className="mt-4">
          <button
            className="rounded-lg bg-violet-600 px-4 py-2 text-sm font-semibold text-white shadow-sm hover:bg-violet-700 disabled:cursor-not-allowed disabled:opacity-50"
            disabled={status === 'loading' || !query.trim()}
            type="submit"
          >
            Search
          </button>
        </div>
      </form>

      <section className="mt-6 rounded-xl border border-slate-200 bg-white p-4 shadow-sm dark:border-slate-800 dark:bg-slate-900">
        {status === 'idle' && (
          <p className="text-sm text-slate-600 dark:text-slate-400">
            Run a retrieval debug search to inspect branch rankings.
          </p>
        )}
        {status === 'loading' && (
          <p className="text-sm text-slate-600 dark:text-slate-400">Loading retrieval branches...</p>
        )}
        {status === 'empty' && (
          <p className="text-sm text-slate-600 dark:text-slate-400">
            No retrieval results matched this query.
          </p>
        )}
        {status === 'error' && errorMessage && (
          <p className="text-sm font-medium text-red-700 dark:text-red-300">{errorMessage}</p>
        )}
        {status === 'results' && response && (
          <ResultsPanel response={response} />
        )}
      </section>
    </main>
  )
}

function ResultsPanel({ response }: { response: RetrievalDebugResponse }) {
  return (
    <div className="space-y-6">
      <ComparativeResultsTable results={response.final_results} />
      <BranchRankings branches={response.branches} />
      {response.diff && <RankingDiffView diff={response.diff} />}
    </div>
  )
}

function ComparativeResultsTable({
  results,
}: {
  results: RetrievalDebugResponse['final_results']
}) {
  return (
    <section>
      <h2 className="text-lg font-semibold text-slate-900 dark:text-slate-100">
        Comparative results
      </h2>
      <div className="mt-3 overflow-x-auto">
        <table className="min-w-full divide-y divide-slate-200 text-sm dark:divide-slate-800">
          <thead className="text-left text-xs uppercase tracking-wide text-slate-500">
            <tr>
              <th className="px-3 py-2">Final</th>
              <th className="px-3 py-2">Chunk</th>
              <th className="px-3 py-2">Title</th>
              <th className="px-3 py-2">Scores</th>
              <th className="px-3 py-2">Strategies</th>
              <th className="px-3 py-2">Metadata</th>
              <th className="px-3 py-2">Reason</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
            {results.map((result) => (
              <tr key={result.chunk_id}>
                <td className="px-3 py-3 font-semibold">#{result.final_position}</td>
                <td className="px-3 py-3">
                  <span>chunk {result.chunk_id} / doc {result.document_id}</span>
                </td>
                <td className="px-3 py-3">
                  <p className="font-medium text-slate-900 dark:text-slate-100">{result.title}</p>
                  <p className="mt-1 max-w-md text-slate-600 dark:text-slate-400">
                    {result.content_excerpt}
                  </p>
                </td>
                <td className="px-3 py-3">
                  <ScoreList result={result} />
                </td>
                <td className="px-3 py-3">
                  <ChipList values={result.source_strategies} />
                </td>
                <td className="px-3 py-3">
                  <MetadataPreview metadata={result.metadata} />
                </td>
                <td className="px-3 py-3">
                  <ResultExplanation explanation={result.explanation} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  )
}

function ScoreList({ result }: { result: RetrievalDebugResponse['final_results'][number] }) {
  const rows = [
    ['semantic', result.semantic_score, result.semantic_rank],
    ['lexical', result.lexical_score, result.lexical_rank],
    ['fusion', result.fusion_score, result.fusion_rank],
    ['rerank', result.rerank_score, result.rerank_rank],
  ] as const
  return (
    <ul className="space-y-1 text-xs text-slate-600 dark:text-slate-400">
      {rows.map(([label, score, rank]) => (
        <li key={label}>
          {label}: {score == null ? 'n/a' : score.toFixed(3)}
          {rank == null ? '' : ` / #${rank}`}
        </li>
      ))}
    </ul>
  )
}

function ChipList({ values }: { values: string[] }) {
  return (
    <div className="flex flex-wrap gap-1">
      {values.map((value) => (
        <span
          className="rounded-full bg-violet-100 px-2 py-0.5 text-xs font-medium text-violet-800 dark:bg-violet-950 dark:text-violet-200"
          key={value}
        >
          {value}
        </span>
      ))}
    </div>
  )
}

function MetadataPreview({ metadata }: { metadata: Record<string, unknown> }) {
  const entries = Object.entries(metadata).slice(0, 3)
  if (entries.length === 0) {
    return <span className="text-xs text-slate-500">none</span>
  }
  return (
    <dl className="space-y-1 text-xs text-slate-600 dark:text-slate-400">
      {entries.map(([key, value]) => (
        <div key={key}>
          <dt className="inline font-medium">{key}: </dt>
          <dd className="inline">{String(value)}</dd>
        </div>
      ))}
    </dl>
  )
}

function ResultExplanation({
  explanation,
}: {
  explanation: RetrievalDebugResponse['final_results'][number]['explanation']
}) {
  return (
    <div>
      <p className="max-w-sm text-sm text-slate-700 dark:text-slate-300">{explanation.summary}</p>
      <div className="mt-2">
        <ChipList values={explanation.signals} />
      </div>
    </div>
  )
}

function BranchRankings({ branches }: { branches: RetrievalDebugResponse['branches'] }) {
  const branchEntries = [
    ['vector', branches.vector],
    ['lexical', branches.lexical],
    ['hybrid', branches.hybrid],
    ['rerank', branches.rerank],
  ] as const
  return (
    <section>
      <h2 className="text-lg font-semibold text-slate-900 dark:text-slate-100">Branch rankings</h2>
      <div className="mt-3 grid gap-3 md:grid-cols-2 xl:grid-cols-4">
        {branchEntries.map(([name, entries]) => (
          <div
            className="rounded-lg border border-slate-200 p-3 dark:border-slate-800"
            key={name}
          >
            <h3 className="font-medium capitalize">{name}</h3>
            {entries === null ? (
              <p className="mt-2 text-sm text-slate-500">{name} not run</p>
            ) : entries.length === 0 ? (
              <p className="mt-2 text-sm text-slate-500">{name} empty</p>
            ) : (
              <ul className="mt-2 space-y-1 text-sm text-slate-700 dark:text-slate-300">
                {entries.map((entry) => (
                  <li key={`${name}:${entry.chunk_id}`}>
                    <span>
                      {name} #{entry.rank}
                    </span>{' '}
                    - chunk {entry.chunk_id} - score {entry.score.toFixed(3)}
                  </li>
                ))}
              </ul>
            )}
          </div>
        ))}
      </div>
    </section>
  )
}

function RankingDiffView({ diff }: { diff: NonNullable<RetrievalDebugResponse['diff']> }) {
  return (
    <section>
      <h2 className="text-lg font-semibold text-slate-900 dark:text-slate-100">Ranking diff</h2>
      <div className="mt-3 grid gap-3 md:grid-cols-2 xl:grid-cols-3">
        <DiffEntries title="Common" entries={diff.common} />
        <DiffEntries title="Vector only" entries={diff.vector_only} />
        <DiffEntries title="Lexical only" entries={diff.lexical_only} />
        <DiffEntries title="Hybrid rescued" entries={diff.hybrid_rescued} />
        <DiffEntries title="Dropped by threshold" entries={diff.dropped_by_threshold} />
        <DiffEntries title="Dropped by rerank" entries={diff.dropped_by_rerank} />
        <div className="rounded-lg border border-slate-200 p-3 dark:border-slate-800">
          <h3 className="font-medium">Big movers</h3>
          {diff.big_movers.length === 0 ? (
            <p className="mt-2 text-sm text-slate-500">none</p>
          ) : (
            <ul className="mt-2 space-y-1 text-sm text-slate-700 dark:text-slate-300">
              {diff.big_movers.map((entry) => (
                <li key={`mover:${entry.chunk_id}`}>
                  chunk {entry.chunk_id} / doc {entry.document_id}:{' '}
                  <span>
                    {entry.from_rank} -&gt; {entry.to_rank}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </section>
  )
}

function DiffEntries({
  entries,
  title,
}: {
  entries: NonNullable<RetrievalDebugResponse['diff']>['common']
  title: string
}) {
  return (
    <div className="rounded-lg border border-slate-200 p-3 dark:border-slate-800">
      <h3 className="font-medium">{title}</h3>
      {entries.length === 0 ? (
        <p className="mt-2 text-sm text-slate-500">none</p>
      ) : (
        <ul className="mt-2 space-y-1 text-sm text-slate-700 dark:text-slate-300">
          {entries.map((entry) => (
            <li key={`${title}:${entry.chunk_id}`}>
              chunk {entry.chunk_id} / doc {entry.document_id}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

function QueryBox({
  disabled,
  onQueryChange,
  onRecentSearch,
  onStrategyChange,
  query,
  recentSearches,
  strategy,
}: {
  disabled: boolean
  onQueryChange: (query: string) => void
  onRecentSearch: (search: RecentSearch) => void
  onStrategyChange: (strategy: RetrievalStrategy) => void
  query: string
  recentSearches: RecentSearch[]
  strategy: RetrievalStrategy
}) {
  return (
    <section>
      <div className="grid gap-3 sm:grid-cols-[minmax(0,1fr)_12rem]">
        <div>
          <label
            className="block text-sm font-medium text-slate-700 dark:text-slate-200"
            htmlFor="retrieval-debug-query"
          >
            Query
          </label>
          <input
            className="mt-2 w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 shadow-sm focus:border-violet-500 focus:outline-none focus:ring-2 focus:ring-violet-200 dark:border-slate-700 dark:bg-slate-950 dark:text-slate-100"
            disabled={disabled}
            id="retrieval-debug-query"
            onChange={(ev) => onQueryChange(ev.target.value)}
            type="search"
            value={query}
          />
        </div>
        <div>
          <label
            className="block text-sm font-medium text-slate-700 dark:text-slate-200"
            htmlFor="retrieval-debug-strategy"
          >
            Strategy
          </label>
          <select
            className="mt-2 w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 dark:border-slate-700 dark:bg-slate-950 dark:text-slate-100"
            disabled={disabled}
            id="retrieval-debug-strategy"
            onChange={(ev) => onStrategyChange(ev.target.value as RetrievalStrategy)}
            value={strategy}
          >
            <option value="all">all</option>
            <option value="vector">vector</option>
            <option value="lexical">lexical</option>
            <option value="hybrid">hybrid</option>
            <option value="rerank">rerank</option>
          </select>
        </div>
      </div>
      {recentSearches.length > 0 && (
        <div className="mt-4">
          <h2 className="text-sm font-medium text-slate-700 dark:text-slate-200">Recent searches</h2>
          <div className="mt-2 flex flex-wrap gap-2">
            {recentSearches.map((search) => (
              <button
                className="rounded-full border border-slate-300 px-3 py-1 text-xs text-slate-700 hover:bg-slate-100 dark:border-slate-700 dark:text-slate-200 dark:hover:bg-slate-800"
                key={`${search.query}:${search.strategy}`}
                onClick={() => onRecentSearch(search)}
                type="button"
              >
                {search.query} ({search.strategy})
              </button>
            ))}
          </div>
        </div>
      )}
    </section>
  )
}

function TuningPanel({
  disabled,
  onChange,
  tuning,
}: {
  disabled: boolean
  onChange: (patch: Partial<TuningState>) => void
  tuning: TuningState
}) {
  const inputClass =
    'mt-1 w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 dark:border-slate-700 dark:bg-slate-950 dark:text-slate-100'
  return (
    <section className="mt-6 grid gap-4 md:grid-cols-2 xl:grid-cols-4">
      <NumberField
        disabled={disabled}
        inputClass={inputClass}
        label="Vector top k"
        onChange={(vectorTopK) => onChange({ vectorTopK })}
        value={tuning.vectorTopK}
      />
      <NumberField
        disabled={disabled}
        inputClass={inputClass}
        label="Semantic threshold"
        onChange={(semanticThreshold) => onChange({ semanticThreshold })}
        step="0.01"
        value={tuning.semanticThreshold}
      />
      <NumberField
        disabled={disabled}
        inputClass={inputClass}
        label="Lexical top k"
        onChange={(lexicalTopK) => onChange({ lexicalTopK })}
        value={tuning.lexicalTopK}
      />
      <NumberField
        disabled={disabled}
        inputClass={inputClass}
        label="Max results"
        onChange={(maxResults) => onChange({ maxResults })}
        value={tuning.maxResults}
      />
      <label className="text-sm font-medium text-slate-700 dark:text-slate-200">
        Hybrid method
        <select
          className={inputClass}
          disabled={disabled}
          onChange={(ev) => onChange({ hybridMethod: ev.target.value as TuningState['hybridMethod'] })}
          value={tuning.hybridMethod}
        >
          <option value="rrf">rrf</option>
          <option value="weighted">weighted</option>
        </select>
      </label>
      <NumberField
        disabled={disabled}
        inputClass={inputClass}
        label="Vector weight"
        onChange={(vectorWeight) => onChange({ vectorWeight })}
        step="0.1"
        value={tuning.vectorWeight}
      />
      <NumberField
        disabled={disabled}
        inputClass={inputClass}
        label="Lexical weight"
        onChange={(lexicalWeight) => onChange({ lexicalWeight })}
        step="0.1"
        value={tuning.lexicalWeight}
      />
      <label className="flex items-center gap-2 text-sm font-medium text-slate-700 dark:text-slate-200">
        <input
          checked={tuning.rerankEnabled}
          disabled={disabled}
          onChange={(ev) => onChange({ rerankEnabled: ev.target.checked })}
          type="checkbox"
        />
        Enable rerank
      </label>
      <TextField
        disabled={disabled}
        inputClass={inputClass}
        label="Client sector"
        onChange={(clientSector) => onChange({ clientSector })}
        value={tuning.clientSector}
      />
      <TextField
        disabled={disabled}
        inputClass={inputClass}
        label="Tags"
        onChange={(tags) => onChange({ tags })}
        value={tuning.tags}
      />
      <NumberField
        disabled={disabled}
        inputClass={inputClass}
        label="Year from"
        onChange={(yearFrom) => onChange({ yearFrom })}
        value={tuning.yearFrom}
      />
      <NumberField
        disabled={disabled}
        inputClass={inputClass}
        label="Year to"
        onChange={(yearTo) => onChange({ yearTo })}
        value={tuning.yearTo}
      />
    </section>
  )
}

function NumberField({
  disabled,
  inputClass,
  label,
  onChange,
  step = '1',
  value,
}: {
  disabled: boolean
  inputClass: string
  label: string
  onChange: (value: string) => void
  step?: string
  value: string
}) {
  return (
    <label className="text-sm font-medium text-slate-700 dark:text-slate-200">
      {label}
      <input
        className={inputClass}
        disabled={disabled}
        onChange={(ev) => onChange(ev.target.value)}
        step={step}
        type="number"
        value={value}
      />
    </label>
  )
}

function TextField({
  disabled,
  inputClass,
  label,
  onChange,
  value,
}: {
  disabled: boolean
  inputClass: string
  label: string
  onChange: (value: string) => void
  value: string
}) {
  return (
    <label className="text-sm font-medium text-slate-700 dark:text-slate-200">
      {label}
      <input
        className={inputClass}
        disabled={disabled}
        onChange={(ev) => onChange(ev.target.value)}
        type="text"
        value={value}
      />
    </label>
  )
}
