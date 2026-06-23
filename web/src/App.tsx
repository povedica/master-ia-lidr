import { shouldShowRetrievalDebugPage } from './appRouting'
import { EstimationWorkbench } from './features/estimation/components/EstimationWorkbench'
import { RetrievalDebugPage } from './features/retrieval-debug/components/RetrievalDebugPage'
import { ThemeControl } from './theme/ThemeControl'
import { useAppearance } from './theme/useAppearance'

function App() {
  const { mode, setMode } = useAppearance()
  const themeControl = <ThemeControl mode={mode} onModeChange={setMode} />
  const retrievalDebugEnabled = import.meta.env.VITE_ENABLE_RETRIEVAL_DEBUG === 'true'
  const showRetrievalDebug = shouldShowRetrievalDebugPage(
    window.location.pathname,
    retrievalDebugEnabled,
  )

  return (
    <div className="min-h-screen bg-slate-50 text-slate-900 dark:bg-slate-950 dark:text-slate-100">
      {showRetrievalDebug ? (
        <RetrievalDebugPage themeControl={themeControl} />
      ) : (
        <EstimationWorkbench
          retrievalDebugHref={retrievalDebugEnabled ? '/debug/retrieval' : undefined}
          themeControl={themeControl}
        />
      )}
    </div>
  )
}

export default App
