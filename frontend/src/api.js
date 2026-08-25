// Client API — même origine (le backend FastAPI sert le build), proxy Vite en dev.
// En build "démo" (GitHub Pages), les appels sont simulés avec des données d'exemple.

export const DEMO = import.meta.env.VITE_DEMO === '1'

async function request(path, options = {}) {
  if (DEMO) {
    const { demoRequest } = await import('./demoApi.js')
    return demoRequest(path, options)
  }
  const res = await fetch(path, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  })
  if (!res.ok) {
    let detail = `${res.status} ${res.statusText}`
    try {
      const data = await res.json()
      if (data.detail) detail = data.detail
    } catch { /* réponse non JSON */ }
    throw new Error(detail)
  }
  return res.json()
}

export const api = {
  health: () => request('/api/health'),

  offers: (params = {}) => {
    const q = new URLSearchParams()
    Object.entries(params).forEach(([k, v]) => {
      if (v !== undefined && v !== null && v !== '') q.set(k, v)
    })
    return request(`/api/offers?${q}`)
  },
  offer: (id) => request(`/api/offers/${id}`),
  updateOffer: (id, body) =>
    request(`/api/offers/${id}`, { method: 'PATCH', body: JSON.stringify(body) }),
  generateLetter: (id) => request(`/api/offers/${id}/letter`, { method: 'POST' }),
  addManualOffer: (body) => request('/api/offers/manual', { method: 'POST', body: JSON.stringify(body) }),
  enrichOffer: (id) => request(`/api/offers/${id}/enrich`, { method: 'POST' }),
  interviewPrep: (id) => request(`/api/offers/${id}/interview-prep`, { method: 'POST' }),
  generateEmail: (id, kind) => request(`/api/offers/${id}/email?kind=${kind}`, { method: 'POST' }),
  gapAnalysis: (id) => request(`/api/offers/${id}/gap-analysis`, { method: 'POST' }),

  addInterview: (id, body) =>
    request(`/api/offers/${id}/interviews`, { method: 'POST', body: JSON.stringify(body) }),
  updateInterview: (id, index, body) =>
    request(`/api/offers/${id}/interviews/${index}`, { method: 'PATCH', body: JSON.stringify(body) }),
  deleteInterview: (id, index) =>
    request(`/api/offers/${id}/interviews/${index}`, { method: 'DELETE' }),

  contacts: (company) => request(`/api/contacts${company ? `?company=${encodeURIComponent(company)}` : ''}`),
  addContact: (body) => request('/api/contacts', { method: 'POST', body: JSON.stringify(body) }),
  deleteContact: (id) => request(`/api/contacts/${id}`, { method: 'DELETE' }),

  profile: () => request('/api/profile'),
  updateProfile: (body) => request('/api/profile', { method: 'PUT', body: JSON.stringify(body) }),
  uploadCv: (file) => {
    if (DEMO) {
      return Promise.reject(
        new Error("Import de CV disponible uniquement dans l'application locale (démo en ligne)."),
      )
    }
    const form = new FormData()
    form.append('file', file)
    return fetch('/api/profile/cv', { method: 'POST', body: form }).then(async (res) => {
      if (!res.ok) {
        const data = await res.json().catch(() => ({}))
        throw new Error(data.detail || res.statusText)
      }
      return res.json()
    })
  },
  rescore: () => request('/api/profile/rescore', { method: 'POST' }),
  scoringDefaults: () => request('/api/profile/scoring-defaults'),

  startScan: () => request('/api/scans', { method: 'POST' }),
  scanStatus: () => request('/api/scans/status'),
  scans: (limit = 10) => request(`/api/scans?limit=${limit}`),

  digestToday: () => request('/api/digests/today'),
  digests: () => request('/api/digests'),
  sendDigestEmail: () => request('/api/digests/send-email', { method: 'POST' }),
  testEmail: () => request('/api/digests/test-email', { method: 'POST' }),

  sources: () => request('/api/sources'),
  stats: () => request('/api/stats'),
  journal: (kind) => request(`/api/journal${kind ? `?kind=${kind}` : ''}`),
  restore: (file) => {
    if (DEMO) {
      return Promise.reject(new Error("Restauration disponible uniquement dans l'application locale (démo en ligne)."))
    }
    const form = new FormData()
    form.append('file', file)
    return fetch('/api/restore', { method: 'POST', body: form }).then(async (res) => {
      if (!res.ok) {
        const data = await res.json().catch(() => ({}))
        throw new Error(data.detail || res.statusText)
      }
      return res.json()
    })
  },
}

export const STATUS_LABELS = {
  nouvelle: 'Nouvelle',
  vue: 'Vue',
  a_postuler: 'À postuler',
  postulee: 'Postulée',
  relancee: 'Relancée',
  entretien: 'Entretien',
  refusee: 'Refusée',
  fermee: 'Fermée',
}

export const STATUS_COLORS = {
  nouvelle: '#0969da',
  vue: '#57606a',
  a_postuler: '#8250df',
  postulee: '#9a6700',
  relancee: '#bc4c00',
  entretien: '#1a7f37',
  refusee: '#cf222e',
  fermee: '#6e7781',
}

export const SOURCE_LABELS = {
  france_travail: 'France Travail',
  adzuna: 'Adzuna',
  jsearch: 'LinkedIn/Indeed (JSearch)',
  wttj: 'Welcome to the Jungle',
  apec: 'APEC',
  hellowork: 'HelloWork',
  manuelle: 'Ajout manuel',
}

// Seuil « pépite » — garder aligné avec GEM_SCORE (backend/app/services/digest.py).
export const GEM_SCORE = 85

export function scoreColor(score) {
  if (score >= 70) return '#1a7f37'
  if (score >= 45) return '#9a6700'
  return '#57606a'
}

export function formatDate(iso) {
  if (!iso) return '—'
  return new Date(iso).toLocaleDateString('fr-FR', { day: '2-digit', month: 'short', year: 'numeric' })
}

// Une action planifiée est « due » si son échéance est aujourd'hui (inclus) ou passée.
export function actionDue(offer) {
  return Boolean(offer.next_action_date) && new Date(offer.next_action_date) <= new Date().setHours(23, 59, 59)
}

// Déclenche le téléchargement d'un fichier servi par le backend (export Excel,
// lettre Word, sauvegarde…). L'appelant garde la responsabilité du garde DEMO.
export function downloadFile(path) {
  const link = document.createElement('a')
  link.href = path
  link.download = ''
  document.body.appendChild(link)
  link.click()
  link.remove()
}
