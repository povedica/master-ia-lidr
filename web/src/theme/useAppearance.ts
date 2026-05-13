import { useCallback, useEffect, useState } from 'react'

import {
  APPEARANCE_STORAGE_KEY,
  normalizeAppearance,
  resolveDark,
  type AppearanceMode,
} from './appearance'

export function useAppearance(): {
  mode: AppearanceMode
  setMode: (next: AppearanceMode) => void
} {
  const [mode, setModeState] = useState<AppearanceMode>(() => {
    if (typeof window === 'undefined') {
      return 'system'
    }
    return normalizeAppearance(localStorage.getItem(APPEARANCE_STORAGE_KEY))
  })

  const setMode = useCallback((next: AppearanceMode) => {
    setModeState(next)
    try {
      localStorage.setItem(APPEARANCE_STORAGE_KEY, next)
    } catch {
      /* ignore quota / private mode */
    }
  }, [])

  useEffect(() => {
    const root = document.documentElement
    const mq = window.matchMedia('(prefers-color-scheme: dark)')
    const sync = (): void => {
      const prefersDark = mq.matches
      root.classList.toggle('dark', resolveDark(mode, prefersDark))
    }
    sync()
    if (mode !== 'system') {
      return
    }
    mq.addEventListener('change', sync)
    return () => mq.removeEventListener('change', sync)
  }, [mode])

  return { mode, setMode }
}
