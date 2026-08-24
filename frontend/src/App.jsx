import { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react'
import { api } from './api.js'
import Dashboard from './components/Dashboard.jsx'
import Offers from './components/Offers.jsx'
import ProfilePage from './components/Profile.jsx'
import Sources from './components/Sources.jsx'

const ToastContext = createContext(() => {})
export const useToast = () => useContext(ToastContext)

const PAGES = [
  { id: 'dashboard', label: 'Tableau de bord', icon: '📊' },
  { id: 'offers', label: 'Offres', icon: '🎯' },
  { id: 'profile', label: 'Profil & CV', icon: '👤' },
  { id: 'sources', label: 'Sources & réglages', icon: '🔌' },
]

export default function App() {
  const [page, setPage] = useState('dashboard')
  const [toast, setToast] = useState(null)
  const [scanning, setScanning] = useState(false)
  const timer = useRef(null)

  const showToast = useCallback((message, isError = false) => {
    setToast({ message, isError })
    clearTimeout(timer.current)
    timer.current = setTimeout(() => setToast(null), 4500)
  }, [])

  // Suivi d'un scan en cours (poll léger).
  useEffect(() => {
    let mounted = true
    const poll = async () => {
      try {
        const status = await api.scanStatus()
        if (mounted) setScanning(Boolean(status.running))
      } catch { /* backend indisponible */ }
    }
    poll()
    const interval = setInterval(poll, 4000)
    return () => { mounted = false; clearInterval(interval) }
  }, [])

  const startScan = async () => {
    try {
      await api.startScan()
      setScanning(true)
      showToast('Scan lancé — les nouvelles offres arrivent dans quelques minutes.')
    } catch (err) {
      showToast(`Impossible de lancer le scan : ${err.message}`, true)
    }
  }

  return (
    <ToastContext.Provider value={showToast}>
      <div className="layout">
        <aside className="sidebar">
          <div className="brand">Job<span>Finder</span></div>
          <div className="subtitle">Recherche QA · Cédric Moretti</div>
          {PAGES.map((p) => (
            <button
              key={p.id}
              className={`nav ${page === p.id ? 'active' : ''}`}
              onClick={() => setPage(p.id)}
            >
              <span>{p.icon}</span> {p.label}
            </button>
          ))}
          <div style={{ padding: '14px 10px' }}>
            <button className="primary" style={{ width: '100%' }} onClick={startScan} disabled={scanning}>
              {scanning ? (<><span className="spin" />Scan en cours…</>) : 'Lancer un scan'}
            </button>
          </div>
          <div className="footer">
            Les offres ne sont jamais fermées automatiquement.<br />
            Scan quotidien + email selon tes réglages.
          </div>
        </aside>
        <main className="content">
          {page === 'dashboard' && <Dashboard scanning={scanning} goToOffers={() => setPage('offers')} />}
          {page === 'offers' && <Offers scanning={scanning} />}
          {page === 'profile' && <ProfilePage />}
          {page === 'sources' && <Sources />}
        </main>
      </div>
      {toast && <div className={`toast ${toast.isError ? 'error' : ''}`}>{toast.message}</div>}
    </ToastContext.Provider>
  )
}
