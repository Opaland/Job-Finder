import { useCallback, useEffect, useState } from 'react'
import { api, DEMO, formatDate, GEM_SCORE, scoreColor, SOURCE_LABELS, STATUS_COLORS, STATUS_LABELS } from '../api.js'
import { useToast } from '../App.jsx'
import OfferDetail from './OfferDetail.jsx'

function AddOfferModal({ onClose, onCreated }) {
  const [form, setForm] = useState({ url: '', title: '', company: '', location: '', raw_text: '' })
  const [saving, setSaving] = useState(false)
  const showToast = useToast()
  const set = (k, v) => setForm((f) => ({ ...f, [k]: v }))

  const submit = async () => {
    if (!form.title.trim() && !form.raw_text.trim() && !form.url.trim()) {
      showToast('Colle au moins le texte de l’annonce, ou donne un titre ou une URL.', true)
      return
    }
    setSaving(true)
    try {
      const offer = await api.addManualOffer(form)
      showToast(`Offre ajoutée et scorée : ${Math.round(offer.final_score)}/100.`)
      onCreated(offer)
    } catch (err) {
      showToast(err.message, true)
    } finally {
      setSaving(false)
    }
  }

  return (
    <>
      <div className="drawer-backdrop" onClick={onClose} />
      <div className="drawer" style={{ width: 'min(560px, 94vw)' }}>
        <button className="close" onClick={onClose}>✕</button>
        <h2>Ajouter une offre à la main</h2>
        <p className="hint">
          Vue sur LinkedIn, Indeed ou ailleurs ? Colle l'annonce ici : elle sera scorée par rapport
          à ton CV et suivie comme les autres. Titre et entreprise sont détectés depuis les deux
          premières lignes si tu les laisses vides.
        </p>
        <div className="section-title">Lien de l'offre</div>
        <input type="text" style={{ width: '100%' }} placeholder="https://…" value={form.url} onChange={(e) => set('url', e.target.value)} />
        <div className="section-title">Texte de l'annonce (collé)</div>
        <textarea rows={10} placeholder={'Titre du poste\nEntreprise\nDescription…'} value={form.raw_text} onChange={(e) => set('raw_text', e.target.value)} />
        <div className="section-title">Titre (optionnel)</div>
        <input type="text" style={{ width: '100%' }} value={form.title} onChange={(e) => set('title', e.target.value)} />
        <div className="section-title">Entreprise / Lieu (optionnels)</div>
        <div style={{ display: 'flex', gap: 8 }}>
          <input type="text" style={{ flex: 1 }} placeholder="Entreprise" value={form.company} onChange={(e) => set('company', e.target.value)} />
          <input type="text" style={{ flex: 1 }} placeholder="Lieu" value={form.location} onChange={(e) => set('location', e.target.value)} />
        </div>
        <div className="actions-row" style={{ marginTop: 16 }}>
          <button className="primary" onClick={submit} disabled={saving}>
            {saving ? (<><span className="spin" />Analyse…</>) : 'Ajouter et scorer'}
          </button>
          <button className="secondary" onClick={onClose}>Annuler</button>
        </div>
      </div>
    </>
  )
}

export default function Offers({ scanning }) {
  const [data, setData] = useState({ total: 0, items: [] })
  const [filters, setFilters] = useState({
    status: '', source: '', min_score: '', search: '', sort: 'score', favorite: '',
  })
  const [selectedId, setSelectedId] = useState(null)
  const [showAdd, setShowAdd] = useState(false)
  const [loading, setLoading] = useState(false)
  const showToast = useToast()

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const params = { ...filters, limit: 200 }
      if (params.favorite === '') delete params.favorite
      setData(await api.offers(params))
    } catch (err) {
      showToast(`Chargement impossible : ${err.message}`, true)
    } finally {
      setLoading(false)
    }
  }, [filters, showToast])

  useEffect(() => { load() }, [load])
  useEffect(() => { if (!scanning) load() }, [scanning]) // rafraîchit à la fin d'un scan

  const setFilter = (key, value) => setFilters((f) => ({ ...f, [key]: value }))

  const updateStatus = async (offer, status) => {
    try {
      await api.updateOffer(offer.id, { status })
      setData((d) => ({
        ...d,
        items: d.items.map((o) => (o.id === offer.id ? { ...o, status } : o)),
      }))
    } catch (err) {
      showToast(err.message, true)
    }
  }

  const toggleFavorite = async (offer) => {
    try {
      await api.updateOffer(offer.id, { favorite: !offer.favorite })
      setData((d) => ({
        ...d,
        items: d.items.map((o) => (o.id === offer.id ? { ...o, favorite: !o.favorite } : o)),
      }))
    } catch (err) {
      showToast(err.message, true)
    }
  }

  return (
    <div>
      <h1>Offres</h1>
      <p className="page-sub">
        {data.total} offre(s) — classées par pertinence par rapport à ton CV.
        Aucune offre n'est fermée sans ton accord.
      </p>

      <div className="filters">
        <input
          type="text"
          placeholder="Rechercher (titre, entreprise, description)…"
          value={filters.search}
          onChange={(e) => setFilter('search', e.target.value)}
        />
        <select value={filters.status} onChange={(e) => setFilter('status', e.target.value)}>
          <option value="">Tous les statuts</option>
          {Object.entries(STATUS_LABELS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
        </select>
        <select value={filters.source} onChange={(e) => setFilter('source', e.target.value)}>
          <option value="">Toutes les sources</option>
          {Object.entries(SOURCE_LABELS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
        </select>
        <select value={filters.min_score} onChange={(e) => setFilter('min_score', e.target.value)}>
          <option value="">Score min.</option>
          <option value="70">≥ 70 — excellent</option>
          <option value="50">≥ 50 — bon</option>
          <option value="30">≥ 30</option>
        </select>
        <select value={filters.favorite} onChange={(e) => setFilter('favorite', e.target.value)}>
          <option value="">Favoris ou non</option>
          <option value="true">★ Favoris</option>
        </select>
        <select value={filters.sort} onChange={(e) => setFilter('sort', e.target.value)}>
          <option value="score">Tri : score</option>
          <option value="date">Tri : date</option>
        </select>
        <button className="primary" onClick={() => setShowAdd(true)}>
          + Ajouter une offre
        </button>
        <button
          className="secondary"
          title="Exporter toutes les offres et leur suivi dans un classeur Excel"
          onClick={() => {
            if (DEMO) {
              showToast("Export Excel disponible uniquement dans l'application locale (démo en ligne).", true)
              return
            }
            const link = document.createElement('a')
            link.href = '/api/offers/export.xlsx'
            link.download = ''
            document.body.appendChild(link)
            link.click()
            link.remove()
          }}
        >
          📊 Exporter en Excel
        </button>
      </div>

      <div className="card" style={{ padding: '4px 14px' }}>
        {loading && <p className="hint">Chargement…</p>}
        {!loading && data.items.length === 0 && (
          <p className="hint" style={{ padding: '14px 0' }}>
            Aucune offre pour ces filtres. Lance un scan depuis la barre latérale pour collecter des offres.
          </p>
        )}
        {data.items.map((offer) => (
          <div className="offer-row" key={offer.id} onClick={() => setSelectedId(offer.id)}>
            <span className="score-badge" style={{ background: scoreColor(offer.final_score) }}>
              {Math.round(offer.final_score)}
            </span>
            <div>
              <div className="title">
                {offer.final_score >= GEM_SCORE && !['postulee', 'relancee', 'entretien', 'refusee', 'fermee'].includes(offer.status) && (
                  <span title={`Pépite : score ≥ ${GEM_SCORE}, pas encore traitée`}>💎 </span>
                )}
                {offer.title}
              </div>
              <div className="meta">
                {offer.company || 'Entreprise non précisée'} · {offer.location || 'Lieu non précisé'} · {formatDate(offer.published_at || offer.collected_at)}
              </div>
              <div style={{ marginTop: 5 }}>
                <span className="chip">{SOURCE_LABELS[offer.source] || offer.source}</span>
                {offer.contract_type && <span className="chip">{offer.contract_type}</span>}
                {offer.remote && <span className="chip remote">Télétravail</span>}
                {!offer.still_online && <span className="chip offline">Plus en ligne ?</span>}
                {offer.salary_text && <span className="chip">{offer.salary_text}</span>}
              </div>
            </div>
            <div className="right" onClick={(e) => e.stopPropagation()}>
              <button
                className={`fav ${offer.favorite ? 'active' : ''}`}
                title="Favori"
                onClick={() => toggleFavorite(offer)}
              >★</button>
              <div style={{ marginTop: 6 }}>
                <select
                  value={offer.status}
                  onChange={(e) => updateStatus(offer, e.target.value)}
                  style={{ borderColor: STATUS_COLORS[offer.status], color: STATUS_COLORS[offer.status], fontWeight: 600 }}
                >
                  {Object.entries(STATUS_LABELS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
                </select>
              </div>
            </div>
          </div>
        ))}
      </div>

      {showAdd && (
        <AddOfferModal
          onClose={() => setShowAdd(false)}
          onCreated={(offer) => { setShowAdd(false); load(); setSelectedId(offer.id) }}
        />
      )}

      {selectedId && (
        <OfferDetail
          offerId={selectedId}
          onClose={() => { setSelectedId(null); load() }}
        />
      )}
    </div>
  )
}
