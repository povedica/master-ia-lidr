export type AppearanceMode = 'light' | 'dark' | 'system'

/** Stable key for client-side theme preference (feature-010). */
export const APPEARANCE_STORAGE_KEY = 'estimador-cag-appearance'

export function normalizeAppearance(raw: string | null): AppearanceMode {
  if (raw === 'light' || raw === 'dark' || raw === 'system') {
    return raw
  }
  return 'system'
}

/** Whether the document root should have the `dark` class (Tailwind class strategy). */
export function resolveDark(mode: AppearanceMode, prefersDark: boolean): boolean {
  if (mode === 'dark') {
    return true
  }
  if (mode === 'light') {
    return false
  }
  return prefersDark
}
