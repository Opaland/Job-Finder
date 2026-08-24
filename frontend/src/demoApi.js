// Mode démo (GitHub Pages) : simule l'API du backend avec des données d'exemple
// produites par le vrai moteur de scoring (et une lettre réellement générée par Claude).
// Les modifications (statuts, notes…) vivent en mémoire le temps de la visite.
import data from './demoData.json'

const state = {
  offers: JSON.parse(JSON.stringify(data.offers)),
  profile: JSON.parse(JSON.stringify(data.profile)),
}

const LOCAL_ONLY =
  "Disponible uniquement dans l'application locale (elle tourne sur ton poste avec ta session Claude Code). " +
  'Ceci est une démo en ligne avec des données d’exemple.'

function offerById(id) {
  return state.offers.find((o) => o.id === Number(id))
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
  if (params.get('sort') === 'date') {
    items.sort((a, b) => (b.collected_at > a.collected_at ? 1 : -1))
  } else {
    items.sort((a, b) => b.final_score - a.final_score)
  }
  return { total: items.length, items }
}

export async function demoRequest(path, options = {}) {
  const [route, query] = path.split('?')
  const method = (options.method || 'GET').toUpperCase()
  const body = options.body ? JSON.parse(options.body) : {}

  if (route === '/api/health') return { ok: true }
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
    }
    return offer
  }

  if (route.match(/^\/api\/offers\/\d+\/letter$/)) throw new Error(LOCAL_ONLY)
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
  if (route === '/api/sources') return data.sources

  throw new Error(`Endpoint non simulé dans la démo : ${route}`)
}
