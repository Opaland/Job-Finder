import { useEffect, useState } from 'react'
import { api, formatDate, scoreColor, SOURCE_LABELS, STATUS_LABELS } from '../api.js'

function OfferLine({ offer }) {
  return (
    <tr>
      <td>
        <span className="score-badge" style={{ background: scoreColor(offer.final_score), minWidth: 38, height: 26, fontSize: 13 }}>
          {Math.round(offer.final_score)}
        </span>
      </td>
      <td>
        <a href={offer.url} target="_blank" rel="noreferrer" style={{ fontWeight: 600 }}>
          {offer.title}
        </a>
        <div className="hint">
          {offer.company || 'Entreprise non précisée'} — {offer.location || 'Lieu non précisé'}
          {offer.remote ? ' · télétravail' : ''}
        </div>
      </td>
      <td>{offer.contract_type || '—'}</td>
      <td>{SOURCE_LABELS[offer.source] || offer.source}</td>
    </tr>
  )
}

export default function Dashboard({ scanning, goToOffers }) {
  const [digest, setDigest] = useState(null)
  const [error, setError] = useState(null)

  const load = async () => {
    try {
      setDigest(await api.digestToday())
      setError(null)
    } catch (err) {
      setError(err.message)
    }
  }

  useEffect(() => { load() }, [])
  useEffect(() => {
    if (!scanning) load()
  }, [scanning])

  if (error) return <p className="error-text">Erreur : {error}</p>
  if (!digest) return <p>Chargement…</p>

  const p = digest.payload
  const counts = p.status_counts || {}
  const scan = p.last_scan

  return (
    <div>
      <h1>Tableau de bord</h1>
      <p className="page-sub">Point du {digest.date} — état des lieux de ta recherche</p>

      <div className="cards-row">
        <div className="stat"><div className="value">{p.total_offers}</div><div className="label">Offres suivies</div></div>
        <div className="stat"><div className="value" style={{ color: '#0969da' }}>{p.new_count}</div><div className="label">Nouvelles (24 h)</div></div>
        <div className="stat"><div className="value" style={{ color: '#8250df' }}>{counts.a_postuler || 0}</div><div className="label">À postuler</div></div>
        <div className="stat"><div className="value" style={{ color: '#9a6700' }}>{counts.postulee || 0}</div><div className="label">Postulées</div></div>
        <div className="stat"><div className="value" style={{ color: '#1a7f37' }}>{counts.entretien || 0}</div><div className="label">Entretiens</div></div>
      </div>

      {p.weekly?.goal > 0 && (
        <div className="card">
          <h2>Objectif de la semaine</h2>
          <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
            <div style={{ flex: 1, background: '#cde2fb', borderRadius: 8, height: 14, overflow: 'hidden' }}>
              <div
                style={{
                  width: `${Math.min(100, (p.weekly.sent / p.weekly.goal) * 100)}%`,
                  background: '#2a78d6', height: '100%', borderRadius: 8,
                  transition: 'width .3s',
                }}
              />
            </div>
            <b style={{ whiteSpace: 'nowrap' }}>
              {p.weekly.sent} / {p.weekly.goal} candidature{p.weekly.goal > 1 ? 's' : ''}
              {p.weekly.sent >= p.weekly.goal ? ' ✅' : ''}
            </b>
          </div>
          <p className="hint" style={{ marginBottom: 0 }}>
            Candidatures envoyées depuis lundi. Objectif réglable dans Profil & CV.
          </p>
        </div>
      )}

      {p.gems?.length > 0 && (
        <div className="card" style={{ borderColor: '#aceebb' }}>
          <h2 style={{ color: '#1a7f37' }}>💎 Pépites à regarder en priorité ({p.gems.length})</h2>
          <p className="hint" style={{ marginTop: 0 }}>Score ≥ 85, pas encore traitées.</p>
          <table className="simple">
            <tbody>{p.gems.map((o) => <OfferLine key={o.id} offer={o} />)}</tbody>
          </table>
        </div>
      )}

      {scan && (
        <div className="card">
          <h2>Dernier scan</h2>
          <p className="hint" style={{ marginTop: 0 }}>
            {scan.finished_at ? `Terminé le ${formatDate(scan.finished_at)} (${scan.trigger})` : 'En cours…'} —{' '}
            <b>{scan.new_count}</b> nouvelle(s) offre(s)
            {scan.error_count > 0 && <span className="warn"> · {scan.error_count} erreur(s) de source (voir Sources & réglages)</span>}
          </p>
        </div>
      )}

      <div className="card">
        <h2>Nouvelles offres ({p.new_count})</h2>
        {p.new_offers?.length ? (
          <table className="simple">
            <tbody>{p.new_offers.map((o) => <OfferLine key={o.id} offer={o} />)}</tbody>
          </table>
        ) : (
          <p className="hint">Aucune nouvelle offre sur les dernières 24 h. Lance un scan ou attends le scan quotidien.</p>
        )}
      </div>

      <div className="card">
        <h2>Top 10 des offres ouvertes</h2>
        {p.top_overall?.length ? (
          <table className="simple">
            <tbody>{p.top_overall.map((o) => <OfferLine key={o.id} offer={o} />)}</tbody>
          </table>
        ) : (
          <p className="hint">Pas encore d'offres. Configure tes sources puis lance un premier scan.</p>
        )}
        <div style={{ marginTop: 10 }}>
          <button className="secondary" onClick={goToOffers}>Voir toutes les offres →</button>
        </div>
      </div>

      {p.to_relaunch?.length > 0 && (
        <div className="card" style={{ borderColor: '#f0b37e' }}>
          <h2 style={{ color: '#bc4c00' }}>⏰ Candidatures à relancer ({p.to_relaunch.length})</h2>
          <p className="hint" style={{ marginTop: 0 }}>
            Postulées ou relancées il y a plus de 7 jours, sans changement depuis.
          </p>
          <table className="simple">
            <tbody>
              {p.to_relaunch.map((o) => (
                <tr key={o.id}>
                  <td style={{ whiteSpace: 'nowrap' }}>
                    <span className="chip">{STATUS_LABELS[o.status] || o.status}</span>
                  </td>
                  <td>
                    <a href={o.url} target="_blank" rel="noreferrer" style={{ fontWeight: 600 }}>{o.title}</a>
                    <div className="hint">{o.company} — {o.location}</div>
                  </td>
                  <td>{Math.round(o.final_score)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {p.to_follow?.length > 0 && (
        <div className="card">
          <h2>Candidatures à suivre</h2>
          <table className="simple">
            <tbody>
              {p.to_follow.map((o) => (
                <tr key={o.id}>
                  <td style={{ whiteSpace: 'nowrap' }}>
                    <span className="chip">{STATUS_LABELS[o.status] || o.status}</span>
                  </td>
                  <td>
                    <a href={o.url} target="_blank" rel="noreferrer" style={{ fontWeight: 600 }}>{o.title}</a>
                    <div className="hint">{o.company} — {o.location}</div>
                  </td>
                  <td>{Math.round(o.final_score)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
