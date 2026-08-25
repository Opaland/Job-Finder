import { useCallback, useEffect, useState } from 'react'
import { actionDue, api, scoreColor, SOURCE_LABELS, STATUS_COLORS, STATUS_LABELS } from '../api.js'
import { useToast } from '../App.jsx'
import OfferDetail from './OfferDetail.jsx'

const COLUMNS = Object.keys(STATUS_LABELS)

export default function Kanban({ scanning }) {
  const [offers, setOffers] = useState([])
  const [selectedId, setSelectedId] = useState(null)
  const [dragOverCol, setDragOverCol] = useState(null)
  const showToast = useToast()

  const [truncated, setTruncated] = useState(0)

  const load = useCallback(async () => {
    try {
      const data = await api.offers({ limit: 2000, sort: 'score' })
      setOffers(data.items)
      setTruncated(Math.max(0, data.total - data.items.length))
    } catch (err) {
      showToast(`Chargement impossible : ${err.message}`, true)
    }
  }, [showToast])

  // Au montage puis quand un scan se termine.
  useEffect(() => { load() }, [load, scanning])

  const moveOffer = async (offerId, status) => {
    const offer = offers.find((o) => o.id === offerId)
    if (!offer || offer.status === status) return
    const previous = offer.status
    setOffers((all) => all.map((o) => (o.id === offerId ? { ...o, status } : o)))
    try {
      await api.updateOffer(offerId, { status })
    } catch (err) {
      setOffers((all) => all.map((o) => (o.id === offerId ? { ...o, status: previous } : o)))
      showToast(`Changement de statut impossible : ${err.message}`, true)
    }
  }

  const onDrop = (e, status) => {
    e.preventDefault()
    setDragOverCol(null)
    const id = Number(e.dataTransfer.getData('text/offer-id'))
    if (id) moveOffer(id, status)
  }

  return (
    <div>
      <h1>Kanban des candidatures</h1>
      <p className="page-sub">
        Glisse une carte d'une colonne à l'autre pour changer son statut — toi seul décides,
        jamais un scan.
        {truncated > 0 && (
          <span className="warn"> Affichage des 2000 meilleures offres ({truncated} non affichées — utilise les filtres de la page Offres).</span>
        )}
      </p>

      <div className="kanban">
        {COLUMNS.map((status) => {
          const cards = offers.filter((o) => o.status === status)
          return (
            <div
              key={status}
              className={`kcol ${dragOverCol === status ? 'drag-over' : ''}`}
              onDragOver={(e) => { e.preventDefault(); setDragOverCol(status) }}
              onDragLeave={() => setDragOverCol(null)}
              onDrop={(e) => onDrop(e, status)}
            >
              <div className="kcol-head" style={{ borderTopColor: STATUS_COLORS[status] }}>
                <span>{STATUS_LABELS[status]}</span>
                <span className="kcount">{cards.length}</span>
              </div>
              <div className="kcards">
                {cards.map((offer) => (
                  <div
                    key={offer.id}
                    className="kcard"
                    draggable
                    onDragStart={(e) => {
                      e.dataTransfer.setData('text/offer-id', String(offer.id))
                      e.dataTransfer.effectAllowed = 'move'
                    }}
                    onClick={() => setSelectedId(offer.id)}
                  >
                    <div className="kcard-top">
                      <span
                        className="score-badge"
                        style={{ background: scoreColor(offer.final_score), minWidth: 34, height: 22, fontSize: 12 }}
                      >
                        {Math.round(offer.final_score)}
                      </span>
                      {offer.favorite && <span style={{ color: '#eac54f' }}>★</span>}
                    </div>
                    <div className="kcard-title">{offer.title}</div>
                    <div className="kcard-meta">
                      {offer.company || 'Entreprise non précisée'}
                      {offer.location ? ` · ${offer.location}` : ''}
                    </div>
                    <div style={{ marginTop: 6 }}>
                      <span className="chip" style={{ marginRight: 4 }}>{SOURCE_LABELS[offer.source] || offer.source}</span>
                      {offer.remote && <span className="chip remote">TT</span>}
                      {actionDue(offer) && <span className="chip offline">⏰</span>}
                    </div>
                  </div>
                ))}
                {cards.length === 0 && <div className="kempty">Déposer ici</div>}
              </div>
            </div>
          )
        })}
      </div>

      {selectedId && (
        <OfferDetail offerId={selectedId} onClose={() => { setSelectedId(null); load() }} />
      )}
    </div>
  )
}
