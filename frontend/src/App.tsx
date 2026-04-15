import './App.css'
import { AgentArenaPage } from './pages/AgentArenaPage'

function App() {
  return (
    <div className="app-shell app-shell--no-sidebar">
      <div className="workspace workspace--full">
        <header className="topbar topbar--slim">
          <span className="topbar__app-name">AgentArena Spectator</span>
        </header>

        <main className="workspace__content">
          <AgentArenaPage />
        </main>
      </div>
    </div>
  )
}

export default App
