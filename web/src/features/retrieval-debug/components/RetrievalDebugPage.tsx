import { type FormEvent, type ReactNode, useState } from 'react'

import {
  RetrievalDebugApiError,
  runRetrievalDebug,
  type RetrievalDebugRequest,
  type RetrievalDebugResponse,
} from '../api/retrievalDebugApi'

type RetrievalDebugStatus = 'idle' | 'loading' | 'results' | 'empty' | 'error'

type RetrievalDebugPageProps = {
  runDebug?: (request: RetrievalDebugRequest) => Promise<RetrievalDebugResponse>
  themeControl?: ReactNode
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

export function RetrievalDebugPage({
  runDebug = runRetrievalDebug,
  themeControl,
}: RetrievalDebugPageProps) {
  const [query, setQuery] = useState('')
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
      const nextResponse = await runDebug({
        query: trimmedQuery,
        strategies: ['all'],
      })
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

      <form className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm dark:border-slate-800 dark:bg-slate-900" onSubmit={onSubmit}>
        <label className="block text-sm font-medium text-slate-700 dark:text-slate-200" htmlFor="retrieval-debug-query">
          Query
        </label>
        <div className="mt-2 flex flex-col gap-3 sm:flex-row">
          <input
            className="min-w-0 flex-1 rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 shadow-sm focus:border-violet-500 focus:outline-none focus:ring-2 focus:ring-violet-200 dark:border-slate-700 dark:bg-slate-950 dark:text-slate-100"
            disabled={status === 'loading'}
            id="retrieval-debug-query"
            onChange={(ev) => setQuery(ev.target.value)}
            type="search"
            value={query}
          />
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
          <p className="text-sm text-slate-600 dark:text-slate-400">
            Showing {response.final_results.length} final retrieval results.
          </p>
        )}
      </section>
    </main>
  )
}
