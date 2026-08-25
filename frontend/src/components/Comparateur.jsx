import { api, formatDate, scoreColor, SOURCE_LABELS, STATUS_LABELS } from '../api.js'
import { useToast } from '../App.jsx'
import { useEffect, useState } from 'react'

// Lignes comparées, dans l'ordre. `valeur` renvoie ce qui s'affiche ; `brut`
// sert à repérer la meilleure des deux (mise en valeur discrète).
const LIGNES = [
  { cle: 'score', libelle: 'Score', valeur: (o) => Math.round(o.final_score), brut: (o) => o.final_score },
  { cle: 'entreprise', libelle: 'Entreprise', valeur: (o) => o.company || '—' },
  { cle: 'lieu', libelle: 'Lieu', valeur: (o) => o.location || '—' },
  { cle: 'remote', libelle: 'Télétravail', valeur: (o) => (o.remote ? 'Oui' : 'Non'), brut: (o) => (o.remote ? 1 : 0) },
  { cle: 'contrat', libelle: 'Contrat', valeur: (o) => o.contract_type || '—' },
  { cle: 'salaire', libelle: 'Salaire affiché', valeur: (o) => o.salary_text || '—' },
  { cle: 'statut', libelle: 'Statut', valeur: (o) => STATUS_LABELS[o.status] || o.status },
  { cle: 'source', libelle: 'Source', valeur: (o) => SOURCE_LABELS[o.source] || o.source },
  { cle: 'publiee', libelle: 'Publiée le', valeur: (o) => formatDate(o.published_at || o.collected_at) },
  { cle: 'ia', libelle: 'Avis de Claude', valeur: (o) => (o.ai_score != null ? `${Math.round(o.ai_score)}/100` : '—'), brut: (o) => o.ai_score ?? -1 },
  { cle: 'entretiens', libelle: 'Entretiens notés', valeur: (o) => (o.interviews || []).length },
]

export default function Comparateur({ idA, idB, onClose }) {
  const [offres, setOffres] = useState(null)
  const showToast = useToast()

  useEffect(() => {
    Promise.all([api.offer(idA), api.offer(idB)])
      .then(setOffres)
      .catch((err) => showToast(err.message, true))
  }, [idA, idB, showToast])

  if (!offres) return null
  const [a, b] = offres

  return (
    <>
      <div className="drawer-backdrop" onClick={onClose} />
      <div className="drawer" style={{ width: 'min(900px, 96vw)' }}>
        <button className="close" onClick={onClose}>✕</button>
        <h2>Comparer deux offres</h2>
        <p className="hint">Les valeurs en gras sont à l'avantage de l'offre concernée.</p>

        <table className="simple">
          <thead>
            <tr>
              <th style={{ width: 150 }}></th>
              {[a, b].map((o) => (
                <th key={o.id}>
                  <a href={o.url} target="_blank" rel="noreferrer">{o.title}</a>
                  <div>
                    <span className="score-badge" style={{ background: scoreColor(o.final_score), minWidth: 38, height: 26, fontSize: 13 }}>
                      {Math.round(o.final_score)}
                    </span>
                  </div>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {LIGNES.map((ligne) => {
              const va = ligne.valeur(a)
              const vb = ligne.valeur(b)
              const ba = ligne.brut ? ligne.brut(a) : null
              const bb = ligne.brut ? ligne.brut(b) : null
              const gagnantA = ba !== null && bb !== null && ba > bb
              const gagnantB = ba !== null && bb !== null && bb > ba
              return (
                <tr key={ligne.cle}>
                  <td className="hint">{ligne.libelle}</td>
                  <td style={{ fontWeight: gagnantA ? 700 : 400 }}>{va}</td>
                  <td style={{ fontWeight: gagnantB ? 700 : 400 }}>{vb}</td>
                </tr>
              )
            })}
          </tbody>
        </table>

        <div className="section-title">Descriptions</div>
        <div style={{ display: 'flex', gap: 12 }}>
          {[a, b].map((o) => (
            <div key={o.id} className="desc" style={{ flex: 1, maxHeight: 320 }}>
              {o.description || 'Description non récupérée.'}
            </div>
          ))}
        </div>
      </div>
    </>
  )
}
