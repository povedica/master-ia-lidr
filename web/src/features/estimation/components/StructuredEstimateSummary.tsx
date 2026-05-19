type StructuredWorkRow = {
  key: string
  phaseLabel: string | null
  name: string
  hours: number
  cost_eur: number
}

function collectStructuredWorkRows(data: Record<string, unknown>): StructuredWorkRow[] {
  const rows: StructuredWorkRow[] = []
  let seq = 0
  const phasesRaw = Array.isArray(data.phases) ? (data.phases as Record<string, unknown>[]) : []
  for (const ph of phasesRaw) {
    const phaseName = typeof ph.name === 'string' ? ph.name.trim() : ''
    const items = Array.isArray(ph.items) ? (ph.items as Record<string, unknown>[]) : []
    for (const it of items) {
      rows.push({
        key: `p-${seq++}`,
        phaseLabel: phaseName.length > 0 ? phaseName : null,
        name: String(it.name ?? ''),
        hours: typeof it.hours === 'number' ? it.hours : 0,
        cost_eur: typeof it.cost_eur === 'number' ? it.cost_eur : 0,
      })
    }
  }
  const lineItemsRaw = Array.isArray(data.line_items)
    ? (data.line_items as Record<string, unknown>[])
    : []
  for (const it of lineItemsRaw) {
    rows.push({
      key: `l-${seq++}`,
      phaseLabel: null,
      name: String(it.name ?? ''),
      hours: typeof it.hours === 'number' ? it.hours : 0,
      cost_eur: typeof it.cost_eur === 'number' ? it.cost_eur : 0,
    })
  }
  return rows
}

function StringListSection({ title, items }: { title: string; items: string[] }) {
  if (items.length === 0) {
    return null
  }
  return (
    <div>
      <h4 className="mb-2 text-sm font-semibold text-slate-900 dark:text-white">{title}</h4>
      <ul className="list-disc space-y-1 pl-5 text-sm text-slate-600 dark:text-slate-300">
        {items.map((item, i) => (
          <li key={`${title}-${i}`}>{item}</li>
        ))}
      </ul>
    </div>
  )
}

function asStringList(value: unknown): string[] {
  if (!Array.isArray(value)) {
    return []
  }
  return value.filter((v): v is string => typeof v === 'string' && v.trim().length > 0)
}

export function StructuredEstimateSummary({ data }: { data: Record<string, unknown> }) {
  const title = typeof data.title === 'string' ? data.title : '—'
  const summary = typeof data.summary === 'string' ? data.summary : ''
  const totals = data.totals as Record<string, unknown> | undefined
  const hours = totals && typeof totals.hours === 'number' ? totals.hours : null
  const cost = totals && typeof totals.cost_eur === 'number' ? totals.cost_eur : null
  const duration =
    typeof data.duration_weeks === 'number' ? data.duration_weeks.toFixed(1) : '—'
  const confidence =
    typeof data.confidence === 'number' ? (data.confidence * 100).toFixed(0) + '%' : '—'

  const workRows = collectStructuredWorkRows(data)
  const showPhaseColumn = workRows.some((r) => r.phaseLabel !== null)

  const metricCards: { label: string; value: string }[] = [
    { label: 'Total hours', value: hours !== null ? String(hours) : '—' },
    { label: 'Total EUR', value: cost !== null ? cost.toLocaleString() : '—' },
    { label: 'Duration (weeks)', value: duration },
    { label: 'Confidence', value: confidence },
  ]

  const assumptions = asStringList(data.assumptions)
  const risks = asStringList(data.risks)
  const recommendedTeam = asStringList(data.recommended_team)
  const nextSteps = asStringList(data.next_steps)

  return (
    <div className="space-y-8">
      <div>
        <h3 className="text-lg font-semibold tracking-tight text-slate-900 dark:text-white">{title}</h3>
        {summary ? (
          <p className="mt-3 max-w-prose text-sm leading-relaxed text-slate-600 dark:text-slate-300">
            {summary}
          </p>
        ) : null}
      </div>
      <dl className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        {metricCards.map(({ label, value }) => (
          <div
            key={label}
            className="rounded-md border border-slate-200 bg-white p-4 dark:border-slate-600 dark:bg-slate-950"
          >
            <dt className="text-[11px] font-medium uppercase tracking-wider text-slate-500 dark:text-slate-400">
              {label}
            </dt>
            <dd className="mt-2 text-2xl font-bold tabular-nums tracking-tight text-slate-900 dark:text-white">
              {value}
            </dd>
          </div>
        ))}
      </dl>
      {workRows.length > 0 ? (
        <div>
          <h4 className="mb-3 text-sm font-semibold text-slate-900 dark:text-white">Effort breakdown</h4>
          <div className="overflow-x-auto rounded-md border border-slate-200 bg-white dark:border-slate-600 dark:bg-slate-950">
            <table className="min-w-full border-collapse text-left text-xs">
              <thead className="bg-slate-100 dark:bg-slate-900">
                <tr>
                  {showPhaseColumn ? (
                    <th className="border-b border-slate-200 px-3 py-2 font-medium text-slate-600 dark:border-slate-700 dark:text-slate-300">
                      Phase
                    </th>
                  ) : null}
                  <th className="border-b border-slate-200 px-3 py-2 font-medium text-slate-600 dark:border-slate-700 dark:text-slate-300">
                    Name
                  </th>
                  <th className="border-b border-slate-200 px-3 py-2 font-medium text-slate-600 dark:border-slate-700 dark:text-slate-300">
                    Hours
                  </th>
                  <th className="border-b border-slate-200 px-3 py-2 font-medium text-slate-600 dark:border-slate-700 dark:text-slate-300">
                    EUR
                  </th>
                </tr>
              </thead>
              <tbody>
                {workRows.map((row) => (
                  <tr
                    key={row.key}
                    className="odd:bg-white even:bg-slate-50 dark:odd:bg-slate-950 dark:even:bg-slate-900/50"
                  >
                    {showPhaseColumn ? (
                      <td className="border-b border-slate-100 px-3 py-2 text-slate-600 dark:border-slate-800 dark:text-slate-300">
                        {row.phaseLabel ?? (row.key.startsWith('l-') ? 'Other' : '—')}
                      </td>
                    ) : null}
                    <td className="border-b border-slate-100 px-3 py-2 text-slate-800 dark:border-slate-800 dark:text-slate-200">
                      {row.name}
                    </td>
                    <td className="border-b border-slate-100 px-3 py-2 tabular-nums text-slate-800 dark:border-slate-800 dark:text-slate-200">
                      {row.hours}
                    </td>
                    <td className="border-b border-slate-100 px-3 py-2 tabular-nums text-slate-800 dark:border-slate-800 dark:text-slate-200">
                      {row.cost_eur}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      ) : null}
      <StringListSection title="Assumptions" items={assumptions} />
      <StringListSection title="Risks" items={risks} />
      <StringListSection title="Recommended team" items={recommendedTeam} />
      <StringListSection title="Next steps" items={nextSteps} />
    </div>
  )
}
