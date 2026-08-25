// Mode démo (GitHub Pages) : simule l'API du backend avec des données d'exemple
// produites par le vrai moteur de scoring (et une lettre réellement générée par Claude).
// Les modifications (statuts, notes…) vivent en mémoire le temps de la visite.
import data from './demoData.json'

const state = {
  offers: JSON.parse(JSON.stringify(data.offers)),
  profile: JSON.parse(JSON.stringify(data.profile)),
  contacts: [
    { id: 1, company: 'Éditeur logiciels santé', name: 'Claire Dupont', role: 'Talent Acquisition', email: 'c.dupont@exemple.fr', phone: '', notes: '' },
  ],
}

const LOCAL_ONLY =
  "Disponible uniquement dans l'application locale (elle tourne sur ton poste avec ta session Claude Code). " +
  'Ceci est une démo en ligne avec des données d’exemple.'

function offerById(id) {
  return state.offers.find((o) => o.id === Number(id))
}

function params_get(query, key) {
  return new URLSearchParams(query).get(key)
}

function listOffers(query) {
  const params = new URLSearchParams(query)
  let items = [...state.offers]
  const status = params.get('status')
  if (status) {
    const wanted = status.split(',')
    items = items.filter((o) => wanted.includes(o.status))
  }
  const source = params.get('source')
  if (source) items = items.filter((o) => o.source === source)
  const minScore = params.get('min_score')
  if (minScore) items = items.filter((o) => o.final_score >= Number(minScore))
  const favorite = params.get('favorite')
  if (favorite) items = items.filter((o) => String(o.favorite) === favorite)
  const search = (params.get('search') || '').toLowerCase()
  if (search) {
    items = items.filter((o) =>
      [o.title, o.company, o.description].join(' ').toLowerCase().includes(search),
    )
  }
  const company = (params.get('company') || '').toLowerCase()
  if (company) items = items.filter((o) => (o.company || '').toLowerCase().includes(company))
  const sort = params.get('sort')
  if (sort === 'date') {
    items.sort((a, b) => (b.collected_at > a.collected_at ? 1 : -1))
  } else if (sort === 'published') {
    items.sort((a, b) => ((b.published_at || '') > (a.published_at || '') ? 1 : -1))
  } else {
    items.sort((a, b) => b.final_score - a.final_score)
  }
  const total = items.length
  const offset = Number(params.get('offset') || 0)
  const limit = Number(params.get('limit') || 100)
  return { total, items: items.slice(offset, offset + limit) }
}

const STATUS_ORDER = ['nouvelle', 'vue', 'a_postuler', 'postulee', 'relancee', 'entretien', 'refusee', 'fermee']
const SOURCE_FR = {
  france_travail: 'France Travail', adzuna: 'Adzuna', jsearch: 'LinkedIn / Indeed',
  wttj: 'Welcome to the Jungle', apec: 'APEC', hellowork: 'HelloWork',
}

function computeStats() {
  const offers = state.offers
  const counts = {}
  offers.forEach((o) => { counts[o.status] = (counts[o.status] || 0) + 1 })
  const sent = ['postulee', 'relancee', 'entretien', 'refusee'].reduce((n, s) => n + (counts[s] || 0), 0)
  const responses = (counts.entretien || 0) + (counts.refusee || 0)
  const open = offers.filter((o) => !['refusee', 'fermee'].includes(o.status))
  const top20 = open.map((o) => o.final_score).sort((a, b) => b - a).slice(0, 20)

  const bySource = {}
  offers.forEach((o) => { bySource[o.source] = (bySource[o.source] || 0) + 1 })

  const bins = Array.from({ length: 10 }, () => 0)
  offers.forEach((o) => { bins[Math.min(9, Math.floor(o.final_score / 10))] += 1 })

  const perDay = []
  for (let i = 29; i >= 0; i--) {
    const d = new Date(Date.now() - i * 86400000)
    const key = d.toISOString().slice(0, 10)
    // Petit historique plausible pour la démo : quelques collectes réparties.
    const count = i === 0 ? offers.length - 3 : ([3, 9, 15, 22].includes(i) ? 1 : 0)
    perDay.push({ date: key, count: Math.max(0, count) })
  }

  const companies = []
  offers.forEach((o) => {
    const applied = (o.status_history || []).find((h) => h.status === 'postulee')
    if (!applied) return
    const pendingDays = Math.max(0, Math.floor((Date.now() - new Date(applied.date)) / 86400000))
    companies.push({
      company: o.company || 'Entreprise non précisée',
      applications: 1,
      responses: ['entretien', 'refusee'].includes(o.status) ? 1 : 0,
      avg_response_days: null,
      pending_days: ['postulee', 'relancee'].includes(o.status) ? pendingDays : null,
    })
  })

  return {
    totals: {
      offers: offers.length,
      new_7d: offers.length - 2,
      sent,
      interviews: counts.entretien || 0,
      response_rate: sent ? Math.round((100 * responses) / sent) : null,
      avg_top20: top20.length ? Math.round((top20.reduce((a, b) => a + b, 0) / top20.length) * 10) / 10 : null,
    },
    by_status: STATUS_ORDER.map((s) => ({ status: s, count: counts[s] || 0 })),
    by_source: Object.entries(bySource)
      .map(([source, count]) => ({ source, label: SOURCE_FR[source] || source, count }))
      .sort((a, b) => b.count - a.count),
    score_bins: bins.map((count, i) => ({ label: i < 9 ? `${i * 10}-${i * 10 + 9}` : '90-100', count })),
    per_day: perDay,
    companies,
  }
}

export async function demoRequest(path, options = {}) {
  const [route, query] = path.split('?')
  const method = (options.method || 'GET').toUpperCase()
  const body = options.body ? JSON.parse(options.body) : {}

  if (route === '/api/health') return { ok: true }
  if (route === '/api/offers/manual' && method === 'POST') {
    const lines = (body.raw_text || '').split('\n').map((l) => l.trim()).filter(Boolean)
    const title = (body.title || '').trim() || (lines[0] || '').slice(0, 120)
    if (!title) throw new Error("Donne au moins un titre, ou colle le texte de l'annonce.")
    const low = ((body.raw_text || '') + ' ' + title).toLowerCase()
    // Score simplifié pour la démo (l'appli locale utilise le vrai moteur).
    const score = /test manager|qa lead|responsable test/.test(low) ? 88 : (/\bqa\b|test/.test(low) ? 62 : 35)
    const offer = {
      id: Math.max(0, ...state.offers.map((o) => o.id)) + 1,
      source: 'manuelle', source_id: `demo-${Date.now()}`,
      title, company: (body.company || '').trim() || (lines[1] && lines[1].length <= 60 ? lines[1] : ''),
      location: (body.location || '').trim(), description: body.raw_text || '',
      url: (body.url || '').trim(), contract_type: /cdi/.test(low) ? 'CDI' : '',
      salary_text: '', remote: /t[ée]l[ée]travail|remote/.test(low),
      published_at: null, collected_at: new Date().toISOString(), last_seen_at: new Date().toISOString(),
      still_online: true, score, ai_score: null, ai_reason: '', final_score: score,
      score_breakdown: [{ label: 'Démo', points: score, max: 100, detail: 'Score simplifié dans la démo — l’application locale applique le vrai moteur pondéré.' }],
      status: 'nouvelle', status_history: [{ status: 'nouvelle', date: new Date().toISOString(), par: 'ajout manuel (démo)' }],
      favorite: false, notes: '', cover_letter: '', interview_prep: null, other_sources: [],
    }
    state.offers.push(offer)
    return offer
  }
  if (route === '/api/offers' && method === 'GET') return listOffers(query)

  const offerMatch = route.match(/^\/api\/offers\/(\d+)$/)
  if (offerMatch) {
    const offer = offerById(offerMatch[1])
    if (!offer) throw new Error('Offre introuvable')
    if (method === 'PATCH') {
      if (body.status && body.status !== offer.status) {
        offer.status = body.status
        offer.status_history = [
          ...(offer.status_history || []),
          { status: body.status, date: new Date().toISOString(), par: 'utilisateur (démo)' },
        ]
      }
      if (body.notes !== undefined) offer.notes = body.notes
      if (body.favorite !== undefined) offer.favorite = body.favorite
      if (body.cover_letter !== undefined) offer.cover_letter = body.cover_letter
      if (body.interview_prep !== undefined) offer.interview_prep = body.interview_prep
      if ('next_action_date' in body) offer.next_action_date = body.next_action_date
      if ('next_action_note' in body) offer.next_action_note = body.next_action_note
    }
    return offer
  }

  if (route.match(/^\/api\/offers\/\d+\/letter$/)) throw new Error(LOCAL_ONLY)
  if (route.match(/^\/api\/offers\/\d+\/enrich$/)) throw new Error(LOCAL_ONLY)
  if (route.match(/^\/api\/offers\/\d+\/interview-prep$/)) throw new Error(LOCAL_ONLY)
  if (route.match(/^\/api\/offers\/\d+\/email$/)) throw new Error(LOCAL_ONLY)
  if (route.match(/^\/api\/offers\/\d+\/gap-analysis$/)) throw new Error(LOCAL_ONLY)
  if (route === '/api/profile/scoring-defaults') {
    // Copie des défauts du backend (source : backend/app/services/scoring.py).
    return { titre: 40, competences: 25, seniorite: 10, localisation: 15, contrat: 5, secteur: 5 }
  }
  if (route === '/api/profile' && method === 'GET') return state.profile
  if (route === '/api/profile' && method === 'PUT') {
    Object.assign(state.profile, body)
    return state.profile
  }
  if (route === '/api/profile/rescore') return { rescored: state.offers.length }
  if (route === '/api/scans' && method === 'POST') throw new Error(LOCAL_ONLY)
  if (route === '/api/scans/status') return { running: false, scan_id: null }
  if (route === '/api/scans') return data.scans
  if (route === '/api/digests/today') return data.digest
  if (route === '/api/digests') return [data.digest]
  if (route.startsWith('/api/digests/')) throw new Error(LOCAL_ONLY)
  if (route === '/api/contacts' && method === 'GET') {
    const company = (params_get(query, 'company') || '').toLowerCase()
    return company
      ? state.contacts.filter((c) => c.company.toLowerCase() === company)
      : state.contacts
  }
  if (route === '/api/contacts' && method === 'POST') {
    const contact = { id: Math.max(0, ...state.contacts.map((c) => c.id)) + 1, role: '', email: '', phone: '', notes: '', ...body }
    state.contacts.push(contact)
    return contact
  }
  const contactMatch = route.match(/^\/api\/contacts\/(\d+)$/)
  if (contactMatch && method === 'DELETE') {
    state.contacts = state.contacts.filter((c) => c.id !== Number(contactMatch[1]))
    return { deleted: true }
  }
  if (route === '/api/sources') return data.sources
  if (route === '/api/stats') return computeStats()
  if (route === '/api/journal') {
    const kind = params_get(query, 'kind')
    const now = Date.now()
    const all = [
      { id: 4, at: new Date(now - 3600e3).toISOString(), kind: 'statut', message: '« Consultant Test Manager » (Cabinet de conseil) : a_postuler → postulee', offer_id: 3 },
      { id: 3, at: new Date(now - 5400e3).toISOString(), kind: 'ia', message: 'Lettre de motivation générée pour « Test Manager H/F ».', offer_id: 1 },
      { id: 2, at: new Date(now - 7200e3).toISOString(), kind: 'scan', message: 'Scan quotidien terminé : 3 nouvelle(s) offre(s), 269 déjà connue(s), 0 erreur(s) de source.', offer_id: null },
      { id: 1, at: new Date(now - 90000e3).toISOString(), kind: 'cv', message: 'CV importé (CV_MORETTI_Cedric.pdf) : 59 compétences détectées, scores recalculés.', offer_id: null },
    ]
    return kind ? all.filter((e) => e.kind === kind) : all
  }
  if (route === '/api/backup') throw new Error(LOCAL_ONLY)

  throw new Error(`Endpoint non simulé dans la démo : ${route}`)
}
