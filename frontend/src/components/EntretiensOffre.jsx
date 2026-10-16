import { useState } from 'react'
import { api } from '../api.js'
import { useToast } from '../App.jsx'

const RESSENTIS = { bon: '😀 bon', mitige: '😐 mitigé', mauvais: '☹️ mauvais' }

export default function EntretiensOffre({ offer, onOfferChange }) {
  const [newInterview, setNewInterview] = useState(null)
  const [report, setReport] = useState(null)
  const showToast = useToast()

  return (
    <>
      <div className="section-title">Entretiens</div>
      {(offer.interviews || []).length === 0 && (
        <p className="hint" style={{ margin: '2px 0 6px' }}>Aucun entretien noté pour cette offre.</p>
      )}
      {(offer.interviews || []).map((e, i) => (
        <div key={i} className="actions-row" style={{ margin: '2px 0' }}>
          <span>
            <b>{new Date(e.date).toLocaleDateString('fr-FR', { day: '2-digit', month: 'short', year: 'numeric' })}</b>
            {' '}{new Date(e.date).toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit' })}
          </span>
          {e.format && <span className="chip">{e.format}</span>}
          {e.interlocuteur && <span className="hint">{e.interlocuteur}</span>}
          {e.ressenti && <span className="chip">{RESSENTIS[e.ressenti] || e.ressenti}</span>}
          <button className="secondary" style={{ padding: '2px 8px', fontSize: 13 }}
            onClick={() => setReport(report?.index === i ? null : {
              index: i, compte_rendu: e.compte_rendu || '', ressenti: e.ressenti || '',
              suite: e.suite || '', relance_le: '',
            })}>
            {e.compte_rendu ? 'Voir le compte-rendu' : 'Compte-rendu'}
          </button>
          <button
            className="fav" title="Supprimer cet entretien" style={{ fontSize: 14 }}
            onClick={async () => {
              // La suppression emporte le compte-rendu de l'entretien avec elle.
              if (!window.confirm("Supprimer cet entretien et son compte-rendu ?")) return
              try { onOfferChange(await api.deleteInterview(offer.id, i)); setReport(null) } catch (err) { showToast(err.message, true) }
            }}
          >✕</button>
        </div>
      ))}
      {report !== null && (
        <div className="card" style={{ padding: 12, margin: '6px 0' }}>
          <div className="section-title" style={{ marginTop: 0 }}>Compte-rendu de l'entretien</div>
          <textarea rows={5} placeholder="Déroulé, questions posées, ce que tu as répondu, points à creuser…"
            value={report.compte_rendu}
            onChange={(ev) => setReport({ ...report, compte_rendu: ev.target.value })} />
          <div className="actions-row" style={{ marginTop: 8 }}>
            <select value={report.ressenti} style={{ width: 150 }}
              onChange={(ev) => setReport({ ...report, ressenti: ev.target.value })}>
              <option value="">Ressenti…</option>
              {Object.entries(RESSENTIS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
            </select>
            <input type="text" placeholder="Suite annoncée (ex. retour sous 8 jours)" style={{ flex: 1, minWidth: 200 }}
              value={report.suite} onChange={(ev) => setReport({ ...report, suite: ev.target.value })} />
          </div>
          <div className="actions-row" style={{ marginTop: 8 }}>
            <span className="hint">Relancer le</span>
            <input type="date" value={report.relance_le}
              onChange={(ev) => setReport({ ...report, relance_le: ev.target.value })} />
            <button className="primary"
              onClick={async () => {
                const body = {
                  compte_rendu: report.compte_rendu, ressenti: report.ressenti, suite: report.suite,
                }
                if (report.relance_le) body.relance_le = `${report.relance_le}T09:00:00`
                try {
                  onOfferChange(await api.updateInterview(offer.id, report.index, body))
                  setReport(null)
                  showToast(report.relance_le
                    ? 'Compte-rendu enregistré, relance planifiée.'
                    : 'Compte-rendu enregistré.')
                } catch (err) { showToast(err.message, true) }
              }}>Enregistrer</button>
            <button className="secondary" onClick={() => setReport(null)}>Fermer</button>
          </div>
        </div>
      )}
      {newInterview === null ? (
        <button className="secondary" style={{ marginTop: 4 }}
          onClick={() => setNewInterview({ date: '', heure: '10:00', format: 'Visio', interlocuteur: '' })}>
          + Noter un entretien
        </button>
      ) : (
        <div className="actions-row" style={{ marginTop: 6 }}>
          <input type="date" value={newInterview.date}
            onChange={(e) => setNewInterview({ ...newInterview, date: e.target.value })} />
          <input type="time" value={newInterview.heure} style={{ width: 110 }}
            onChange={(e) => setNewInterview({ ...newInterview, heure: e.target.value })} />
          <select value={newInterview.format} style={{ width: 120 }}
            onChange={(e) => setNewInterview({ ...newInterview, format: e.target.value })}>
            <option>Visio</option><option>Téléphone</option><option>Sur site</option>
          </select>
          <input type="text" placeholder="Interlocuteur" style={{ width: 170 }} value={newInterview.interlocuteur}
            onChange={(e) => setNewInterview({ ...newInterview, interlocuteur: e.target.value })} />
          <button className="primary"
            onClick={async () => {
              if (!newInterview.date) { showToast("Choisis au moins une date d'entretien.", true); return }
              try {
                onOfferChange(await api.addInterview(offer.id, {
                  date: `${newInterview.date}T${newInterview.heure || '10:00'}:00`,
                  format: newInterview.format,
                  interlocuteur: newInterview.interlocuteur,
                }))
                setNewInterview(null)
                // Le backend retrie la liste : un compte-rendu ouvert viserait
                // désormais un autre entretien (les routes adressent par position).
                setReport(null)
                showToast('Entretien noté — il apparaîtra sur le tableau de bord.')
              } catch (err) { showToast(err.message, true) }
            }}
          >OK</button>
          <button className="secondary" onClick={() => setNewInterview(null)}>Annuler</button>
        </div>
      )}
    </>
  )
}
