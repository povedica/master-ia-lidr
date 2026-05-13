import type { AppearanceMode } from './appearance'

const OPTIONS: readonly { value: AppearanceMode; label: string }[] = [
  { value: 'system', label: 'System' },
  { value: 'light', label: 'Light' },
  { value: 'dark', label: 'Dark' },
] as const

export function ThemeControl({
  mode,
  onModeChange,
}: {
  mode: AppearanceMode
  onModeChange: (next: AppearanceMode) => void
}) {
  return (
    <div
      role="radiogroup"
      aria-label="Appearance"
      className="inline-flex rounded-lg border border-slate-300 bg-slate-100/80 p-0.5 shadow-sm dark:border-slate-600 dark:bg-slate-900/60 dark:shadow-none"
    >
      {OPTIONS.map(({ value, label }) => {
        const selected = mode === value
        return (
          <button
            key={value}
            type="button"
            role="radio"
            aria-checked={selected}
            onClick={() => onModeChange(value)}
            className={
              selected
                ? 'rounded-md bg-violet-600 px-3 py-1.5 text-xs font-medium text-white shadow-sm focus:outline-none focus-visible:ring-2 focus-visible:ring-violet-400 focus-visible:ring-offset-2 focus-visible:ring-offset-slate-100 dark:focus-visible:ring-offset-slate-900'
                : 'rounded-md px-3 py-1.5 text-xs font-medium text-slate-700 hover:bg-white/80 focus:outline-none focus-visible:ring-2 focus-visible:ring-violet-500 focus-visible:ring-offset-2 focus-visible:ring-offset-slate-100 dark:text-slate-300 dark:hover:bg-slate-800/80 dark:focus-visible:ring-offset-slate-900'
            }
          >
            {label}
          </button>
        )
      })}
    </div>
  )
}
