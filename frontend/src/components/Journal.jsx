import { useEffect, useState } from 'react'
import { api } from '../api.js'
import { useToast } from '../App.jsx'

const KIND_META = {
  scan: ['🔎', 'Scan'],
  statut: ['📌', 'Statut'],
  ia: ['🤖', 'IA'],
  ajout: ['➕', 'Ajout'],
  cv: ['📄', 'CV'],
  restauration: ['💾', 'Restauration'],
}

export default function Journal() {
  const [entries, setEntries] = useState(null)
  const [failed, setFailed] = useState(false)
  const [retry, setRetry] = useState(0)
  const [kind, setKind] = useState('')
  const showToast = useToast()

  useEffect(() => {
    setEntries(null)
    setFailed(false)
    api.journal(kind).then(setEntries).catch((err) => {
      setFailed(true)
      setEntries([])
      showToast(`Journal indisponible : ${err.message}`, true)
    })
  }, [kind, retry, showToast])

  if (entries === null) return <p>Chargement…</p>

  // Regroupe par jour.
  const byDay = entries.reduce((acc, e) => {
    const day = new Date(e.at).toLocaleDateString('fr-FR', { weekday: 'long', day: '2-digit', month: 'long' })
    ;(acc[day] = acc[day] || []).push(e)
    return acc
  }, {})

  return (
    <div>
      <h1>Journal d'activité</h1>
      <p className="page-sub">Tout ce qui s'est passé : scans, statuts, générations IA, ajouts…</p>

      <div className="filters">
        <select value={kind} onChange={(e) => setKind(e.target.value)}>
          <option value="">Tous les événements</option>
          {Object.entries(KIND_META).map(([k, [, label]]) => (
            <option key={k} value={k}>{label}</option>
          ))}
        </select>
      </div>

      {failed && (
        <div className="card">
          <p className="hint">Le journal n'a pas pu être chargé.</p>
          <button className="secondary" onClick={() => setRetry((r) => r + 1)}>Réessayer</button>
        </div>
      )}
      {!failed && entries.length === 0 && (
        <div className="card"><p className="hint">Aucun événement pour l'instant — lance un scan !</p></div>
      )}

      {Object.entries(byDay).map(([day, dayEntries]) => (
        <div className="card" key={day}>
          <h2 style={{ textTransform: 'capitalize' }}>{day}</h2>
          <table className="simple">
            <tbody>
              {dayEntries.map((e) => {
                const [icon, label] = KIND_META[e.kind] || ['•', e.kind]
                return (
                  <tr key={e.id}>
                    <td style={{ whiteSpace: 'nowrap' }} className="hint">
                      {new Date(e.at).toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit' })}
                    </td>
                    <td style={{ whiteSpace: 'nowrap' }}><span className="chip">{icon} {label}</span></td>
                    <td>{e.message}</td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      ))}
    </div>
  )
}
