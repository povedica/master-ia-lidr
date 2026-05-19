import { cloneElement, type ReactElement } from 'react'

const CONTROL_ERR_RING =
  'ring-2 ring-red-500/45 ring-offset-2 ring-offset-white dark:ring-offset-slate-950'

export const INPUT_CLASS =
  'w-full rounded border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 focus:outline-none focus-visible:border-teal-500 focus-visible:ring-2 focus-visible:ring-teal-500 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100'

export function Field({
  name,
  label,
  error,
  hint,
  required,
  children,
}: {
  name: string
  label: string
  error?: string
  hint?: string
  required?: boolean
  children: ReactElement<Record<string, unknown>>
}) {
  const hintId = `${name}-hint`
  const errId = `${name}-error`
  const invalid = Boolean(error)
  const describedByParts: string[] = []
  if (hint) {
    describedByParts.push(hintId)
  }
  if (invalid) {
    describedByParts.push(errId)
  }
  const describedBy = describedByParts.length > 0 ? describedByParts.join(' ') : undefined
  const childProps = children.props as { className?: string }
  const childClass = childProps.className
  const child = cloneElement(children, {
    id: name,
    name,
    'aria-invalid': invalid ? true : undefined,
    'aria-describedby': describedBy,
    'aria-required': required ? true : undefined,
    className: invalid ? [childClass, CONTROL_ERR_RING].filter(Boolean).join(' ') : childClass,
  } as Record<string, unknown>)
  const labelText = required ? `${label} *` : label
  return (
    <div className="space-y-0">
      <label
        htmlFor={name}
        className="mb-1 block text-xs font-medium uppercase tracking-wide text-slate-500 dark:text-slate-400"
      >
        {labelText}
      </label>
      {hint ? (
        <p id={hintId} className="mb-1.5 text-xs text-slate-500 dark:text-slate-400">
          {hint}
        </p>
      ) : null}
      {child}
      {error ? (
        <p id={errId} role="alert" className="mt-1.5 text-sm text-red-600 dark:text-red-400">
          {error}
        </p>
      ) : null}
    </div>
  )
}
