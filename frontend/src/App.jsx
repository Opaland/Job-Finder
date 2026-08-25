import { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react'
import { api, DEMO } from './api.js'
import Dashboard from './components/Dashboard.jsx'
import Journal from './components/Journal.jsx'
import Kanban from './components/Kanban.jsx'
import Marche from './components/Marche.jsx'
import Palette from './components/Palette.jsx'
import Offers from './components/Offers.jsx'
import ProfilePage from './components/Profile.jsx'
import Sources from './components/Sources.jsx'
import Stats from './components/Stats.jsx'

const ToastContext = createContext(() => {})
export const useToast = () => useContext(ToastContext)

const PAGES = [
  { id: 'dashboard', label: 'Tableau de bord', icon: '🏠' },
  { id: 'offers', label: 'Offres', icon: '🎯' },
  { id: 'kanban', label: 'Kanban', icon: '🗂️' },
  { id: 'stats', label: 'Statistiques', icon: '📊' },
  { id: 'marche', label: 'Marché', icon: '📈' },
  { id: 'journal', label: 'Journal', icon: '📜' },
  { id: 'profile', label: 'Profil & CV', icon: '👤' },
  { id: 'sources', label: 'Sources & réglages', icon: '🔌' },
]

// Raccourci affiché en face de chaque page dans la palette (voir onKeyDown).
const RACCOURCIS_PAGE = {
  dashboard: 'D', offers: 'O', kanban: 'K', stats: 'S',
  marche: 'M', journal: 'J', profile: 'P', sources: 'R',
}

function initialTheme() {
  let theme = 'light'
  try {
    theme = localStorage.getItem('jf_theme') === 'dark' ? 'dark' : 'light'
  } catch { /* stockage indisponible */ }
  // Appliqué immédiatement : les composants (graphiques) lisent l'attribut au rendu.
  document.documentElement.dataset.theme = theme
  return theme
}

export default function App() {
  const [page, setPage] = useState('dashboard')
  const [toast, setToast] = useState(null)
  const [scanning, setScanning] = useState(false)
  const [theme, setTheme] = useState(initialTheme)
  const [palette, setPalette] = useState(false)
  const timer = useRef(null)

  const toggleTheme = () => {
    const next = theme === 'dark' ? 'light' : 'dark'
    // Attribut posé AVANT le re-rendu React, pour que les graphiques lisent le bon thème.
    document.documentElement.dataset.theme = next
    try { localStorage.setItem('jf_theme', next) } catch { /* stockage indisponible */ }
    setTheme(next)
  }

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

  // Raccourcis clavier globaux. Ignorés pendant une saisie : taper « o » dans
  // un champ de recherche ne doit pas changer de page.
  useEffect(() => {
    const dansUnChamp = (cible) =>
      ['INPUT', 'TEXTAREA', 'SELECT'].includes(cible?.tagName) || cible?.isContentEditable

    const onKeyDown = (e) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault()
        setPalette((ouverte) => !ouverte)
        return
      }
      if (e.key === 'Escape') { setPalette(false); return }
      if (e.ctrlKey || e.metaKey || e.altKey || dansUnChamp(e.target)) return

      const versPage = { d: 'dashboard', o: 'offers', k: 'kanban', s: 'stats', m: 'marche', j: 'journal', p: 'profile', r: 'sources' }
      const cible = versPage[e.key.toLowerCase()]
      if (cible) { e.preventDefault(); setPage(cible) }
      if (e.key === '?') { e.preventDefault(); setPalette(true) }
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [])

  return (
    <ToastContext.Provider value={showToast}>
      {DEMO && (
        <div className="demo-banner">
          🎬 Démo en ligne avec des données d'exemple — l'application complète (scans réels, IA, email)
          tourne en local : <a href="https://github.com/Opaland/Job-Finder#1-démarrage-rapide-windows">guide d'installation</a>
        </div>
      )}
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
          <div style={{ padding: '0 10px' }}>
            <button
              className="nav"
              onClick={toggleTheme}
              title="Basculer le thème"
            >
              <span>{theme === 'dark' ? '☀️' : '🌙'}</span> {theme === 'dark' ? 'Mode clair' : 'Mode sombre'}
            </button>
          </div>
          <div className="footer">
            Les offres ne sont jamais fermées automatiquement.<br />
            Scan quotidien + email selon tes réglages.
          </div>
        </aside>
        <main className="content">
          {palette && (
            <Palette
              onClose={() => setPalette(false)}
              commandes={[
                ...PAGES.map((p) => ({
                  id: `page-${p.id}`, libelle: `Aller à ${p.label}`,
                  raccourci: RACCOURCIS_PAGE[p.id], action: () => setPage(p.id),
                })),
                { id: 'scan', libelle: 'Lancer un scan maintenant', action: startScan },
                {
                  id: 'theme', libelle: theme === 'dark' ? 'Passer en mode clair' : 'Passer en mode sombre',
                  action: toggleTheme,
                },
              ]}
            />
          )}

          {page === 'dashboard' && <Dashboard scanning={scanning} goToOffers={() => setPage('offers')} />}
          {page === 'offers' && <Offers scanning={scanning} />}
          {page === 'kanban' && <Kanban scanning={scanning} />}
          {page === 'stats' && <Stats />}
          {page === 'marche' && <Marche />}
          {page === 'journal' && <Journal />}
          {page === 'profile' && <ProfilePage />}
          {page === 'sources' && <Sources />}
        </main>
      </div>
      {toast && <div className={`toast ${toast.isError ? 'error' : ''}`}>{toast.message}</div>}
    </ToastContext.Provider>
  )
}
