import { EstimationWorkbench } from './features/estimation/components/EstimationWorkbench'
import { ThemeControl } from './theme/ThemeControl'
import { useAppearance } from './theme/useAppearance'

function App() {
  const { mode, setMode } = useAppearance()
  return (
    <div className="min-h-screen bg-slate-50 text-slate-900 dark:bg-slate-950 dark:text-slate-100">
      <div className="border-b border-slate-200 dark:border-slate-800">
        <div className="mx-auto flex max-w-3xl items-center justify-end px-4 py-3">
          <ThemeControl mode={mode} onModeChange={setMode} />
        </div>
      </div>
      <EstimationWorkbench />
    </div>
  )
}

export default App
