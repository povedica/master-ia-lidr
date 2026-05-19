import { EstimationWorkbench } from './features/estimation/components/EstimationWorkbench'
import { ThemeControl } from './theme/ThemeControl'
import { useAppearance } from './theme/useAppearance'

function App() {
  const { mode, setMode } = useAppearance()
  return (
    <div className="min-h-screen bg-slate-50 text-slate-900 dark:bg-slate-950 dark:text-slate-100">
      <EstimationWorkbench themeControl={<ThemeControl mode={mode} onModeChange={setMode} />} />
    </div>
  )
}

export default App
