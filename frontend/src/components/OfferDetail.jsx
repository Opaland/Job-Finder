import { useEffect, useState } from 'react'
import { api, DEMO, formatDate, scoreColor, SOURCE_LABELS, STATUS_COLORS, STATUS_LABELS } from '../api.js'
import { useToast } from '../App.jsx'

const DEMO_ONLY_MSG = "Disponible uniquement dans l'application locale (ceci est la démo en ligne)."

export default function OfferDetail({ offerId, onClose }) {
  const [offer, setOffer] = useState(null)
  const [notes, setNotes] = useState('')
  const [letter, setLetter] = useState('')
  const [generating, setGenerating] = useState(false)
  const [enriching, setEnriching] = useState(false)
  const showToast = useToast()

  useEffect(() => {
    api.offer(offerId).then((o) => {
      setOffer(o)
      setNotes(o.notes || '')
      setLetter(o.cover_letter || '')
      if (o.status === 'nouvelle') {
        api.updateOffer(o.id, { status: 'vue' }).then(setOffer).catch(() => {})
      }
    }).catch((err) => showToast(err.message, true))
  }, [offerId, showToast])

  if (!offer) return null

  const patch = async (body, message) => {
    try {
      const updated = await api.updateOffer(offer.id, body)
      setOffer(updated)
      if (message) showToast(message)
    } catch (err) {
      showToast(err.message, true)
    }
  }

  const generate = async () => {
    setGenerating(true)
    try {
      const updated = await api.generateLetter(offer.id)
      setOffer(updated)
      setLetter(updated.cover_letter)
      showToast('Lettre générée par Claude à partir de ta lettre type et de ton CV.')
    } catch (err) {
      showToast(err.message, true)
    } finally {
      setGenerating(false)
    }
  }

  return (
    <>
      <div className="drawer-backdrop" onClick={onClose} />
      <div className="drawer">
        <button className="close" onClick={onClose}>✕</button>

        <span className="score-badge" style={{ background: scoreColor(offer.final_score) }}>
          {Math.round(offer.final_score)}
        </span>
        <h2>{offer.title}</h2>
        <div className="company">
          {offer.company || 'Entreprise non précisée'} · {offer.location || 'Lieu non précisé'} ·{' '}
          {formatDate(offer.published_at || offer.collected_at)} · via {SOURCE_LABELS[offer.source] || offer.source}
        </div>

        <div className="actions-row">
          <a href={offer.url} target="_blank" rel="noreferrer">
            <button className="primary">Voir l'offre sur le site →</button>
          </a>
          <select
            value={offer.status}
            onChange={(e) => patch({ status: e.target.value })}
            style={{ borderColor: STATUS_COLORS[offer.status], color: STATUS_COLORS[offer.status], fontWeight: 700 }}
          >
            {Object.entries(STATUS_LABELS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </select>
          <button
            className="secondary"
            onClick={() => patch({ favorite: !offer.favorite }, offer.favorite ? 'Retirée des favoris' : 'Ajoutée aux favoris')}
          >
            {offer.favorite ? '★ Favori' : '☆ Mettre en favori'}
          </button>
          {offer.contract_type && <span className="chip">{offer.contract_type}</span>}
          {offer.remote && <span className="chip remote">Télétravail</span>}
          {offer.salary_text && <span className="chip">{offer.salary_text}</span>}
        </div>

        {offer.other_sources?.length > 0 && (
          <p className="hint">
            Aussi vue sur :{' '}
            {offer.other_sources.map((s, i) => (
              <span key={i}>
                <a href={s.url} target="_blank" rel="noreferrer">{SOURCE_LABELS[s.source] || s.source}</a>{' '}
              </span>
            ))}
          </p>
        )}

        <div className="section-title">Pourquoi ce score ?</div>
        <div className="breakdown">
          {(offer.score_breakdown || []).map((item, i) => (
            <div className="item" key={i}>
              <div className="head">
                <span>{item.label}</span>
                <span>{item.max ? `${item.points} / ${item.max}` : ''}</span>
              </div>
              {item.max > 0 && (
                <div className="bar-bg">
                  <div
                    className="bar-fill"
                    style={{ width: `${(item.points / item.max) * 100}%`, background: scoreColor((item.points / item.max) * 100) }}
                  />
                </div>
              )}
              <div className="detail">{item.detail}</div>
            </div>
          ))}
        </div>

        {offer.ai_score != null && (
          <div className="ai-box">
            <b>Avis de Claude (session locale) : {Math.round(offer.ai_score)}/100.</b> {offer.ai_reason}
          </div>
        )}

        <div className="section-title">Description</div>
        {(offer.description || '').length < 400 && (
          <div className="actions-row" style={{ margin: '4px 0 8px' }}>
            <button
              className="secondary"
              disabled={enriching}
              onClick={async () => {
                if (DEMO) { showToast(DEMO_ONLY_MSG, true); return }
                setEnriching(true)
                try {
                  const updated = await api.enrichOffer(offer.id)
                  setOffer(updated)
                  showToast('Description complète récupérée — score recalculé.')
                } catch (err) {
                  showToast(err.message, true)
                } finally {
                  setEnriching(false)
                }
              }}
            >
              {enriching ? (<><span className="spin" style={{ borderTopColor: '#57606a' }} />Récupération…</>) : 'Récupérer la description complète depuis le site'}
            </button>
          </div>
        )}
        <div className="desc">{offer.description || 'Description non récupérée — ouvre l’offre sur le site d’origine.'}</div>

        <div className="section-title">Lettre de motivation adaptée</div>
        <div className="actions-row" style={{ margin: '4px 0 8px' }}>
          <button className="primary" onClick={generate} disabled={generating}>
            {generating ? (<><span className="spin" />Génération en cours…</>) : (letter ? 'Régénérer avec Claude' : 'Générer avec Claude')}
          </button>
          {letter && (
            <button
              className="secondary"
              onClick={() => { navigator.clipboard.writeText(letter); showToast('Lettre copiée dans le presse-papiers.') }}
            >
              Copier la lettre
            </button>
          )}
          {letter && (
            <button
              className="secondary"
              onClick={async () => {
                if (DEMO) { showToast(DEMO_ONLY_MSG, true); return }
                if (letter !== offer.cover_letter) {
                  try {
                    setOffer(await api.updateOffer(offer.id, { cover_letter: letter }))
                  } catch (err) {
                    showToast(`Lettre non sauvegardée (${err.message}) — export annulé.`, true)
                    return
                  }
                }
                const link = document.createElement('a')
                link.href = `/api/offers/${offer.id}/letter.docx`
                link.download = ''
                document.body.appendChild(link)
                link.click()
                link.remove()
              }}
            >
              Télécharger en Word (.docx)
            </button>
          )}
        </div>
        <textarea
          rows={letter ? 16 : 4}
          placeholder="La lettre générée apparaîtra ici — tu peux aussi écrire ou coller la tienne."
          value={letter}
          onChange={(e) => setLetter(e.target.value)}
          onBlur={() => letter !== offer.cover_letter && patch({ cover_letter: letter }, 'Lettre enregistrée.')}
        />

        <div className="section-title">Tes notes</div>
        <textarea
          rows={4}
          placeholder="Contact, relance prévue, impressions…"
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
          onBlur={() => notes !== offer.notes && patch({ notes }, 'Notes enregistrées.')}
        />

        {offer.status_history?.length > 1 && (
          <>
            <div className="section-title">Historique</div>
            <ul className="hint">
              {offer.status_history.map((h, i) => (
                <li key={i}>{formatDate(h.date)} — {STATUS_LABELS[h.status] || h.status} ({h.par})</li>
              ))}
            </ul>
          </>
        )}
      </div>
    </>
  )
}
