import { useEffect, useState } from 'react'
import { api, DEMO, downloadFile, formatDate, scoreColor, SOURCE_LABELS, STATUS_COLORS, STATUS_LABELS } from '../api.js'
import { useToast } from '../App.jsx'

const DEMO_ONLY_MSG = "Disponible uniquement dans l'application locale (ceci est la démo en ligne)."

export default function OfferDetail({ offerId, onClose }) {
  const [offer, setOffer] = useState(null)
  const [notes, setNotes] = useState('')
  const [letter, setLetter] = useState('')
  const [prep, setPrep] = useState('')
  const [actionNote, setActionNote] = useState('')
  // Action longue en cours : 'lettre' | 'gap' | 'prep' | 'enrich' | 'email:candidature' | 'email:relance'.
  const [busy, setBusy] = useState(null)
  const [emailDraft, setEmailDraft] = useState(null)
  const [contacts, setContacts] = useState([])
  const [newContact, setNewContact] = useState(null)
  const [newInterview, setNewInterview] = useState(null)
  const showToast = useToast()

  const loadContacts = (company) => {
    if (!company) return
    api.contacts(company).then(setContacts).catch(() => {})
  }

  // Mécanique commune des générations IA et de l'enrichissement : une seule à la
  // fois, toast de succès ou d'erreur (en démo, l'API simulée explique la limite).
  const runAction = async (name, action, successMessage) => {
    setBusy(name)
    try {
      await action()
      if (successMessage) showToast(successMessage)
    } catch (err) {
      showToast(err.message, true)
    } finally {
      setBusy(null)
    }
  }

  const generateEmail = (kind) => runAction(`email:${kind}`, async () => {
    const email = await api.generateEmail(offerId, kind)
    setEmailDraft({ kind, ...email })
  }, `Email de ${kind} généré — copie-le ou ouvre-le dans ton client mail.`)

  useEffect(() => {
    api.offer(offerId).then((o) => {
      setOffer(o)
      setNotes(o.notes || '')
      setLetter(o.cover_letter || '')
      setPrep(o.interview_prep || '')
      setActionNote(o.next_action_note || '')
      loadContacts(o.company)
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

  const generate = () => runAction('lettre', async () => {
    const updated = await api.generateLetter(offer.id)
    setOffer(updated)
    setLetter(updated.cover_letter)
  }, 'Lettre générée par Claude à partir de ta lettre type et de ton CV.')

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
              disabled={busy !== null}
              onClick={() => runAction('enrich', async () => {
                setOffer(await api.enrichOffer(offer.id))
              }, 'Description complète récupérée — score recalculé.')}
            >
              {busy === 'enrich' ? (<><span className="spin" style={{ borderTopColor: '#57606a' }} />Récupération…</>) : 'Récupérer la description complète depuis le site'}
            </button>
          </div>
        )}
        <div className="desc">{offer.description || 'Description non récupérée — ouvre l’offre sur le site d’origine.'}</div>

        <div className="section-title">Lettre de motivation adaptée</div>
        <div className="actions-row" style={{ margin: '4px 0 8px' }}>
          <button className="primary" onClick={generate} disabled={busy !== null}>
            {busy === 'lettre' ? (<><span className="spin" />Génération en cours…</>) : (letter ? 'Régénérer avec Claude' : 'Générer avec Claude')}
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
                downloadFile(`/api/offers/${offer.id}/letter.docx`)
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

        <div className="section-title">Adéquation CV ↔ offre</div>
        <div className="actions-row" style={{ margin: '4px 0 8px' }}>
          <button
            className="secondary"
            disabled={busy !== null}
            onClick={() => runAction('gap', async () => {
              setOffer(await api.gapAnalysis(offer.id))
            }, "Analyse d'écart générée : couvert, manquant, adaptations du CV, verdict.")}
          >
            {busy === 'gap'
              ? (<><span className="spin" style={{ borderTopColor: '#57606a' }} />Analyse en cours…</>)
              : (offer.gap_analysis ? "🔍 Régénérer l'analyse d'écart CV ↔ offre" : "🔍 Analyser l'écart CV ↔ offre")}
          </button>
        </div>
        {offer.gap_analysis && <div className="desc" style={{ maxHeight: 300 }}>{offer.gap_analysis}</div>}

        <div className="section-title">Emails</div>
        <div className="actions-row" style={{ margin: '4px 0 8px' }}>
          <button className="secondary" disabled={busy !== null} onClick={() => generateEmail('candidature')}>
            {busy === 'email:candidature' ? (<><span className="spin" style={{ borderTopColor: '#57606a' }} />Rédaction…</>) : '✉️ Email de candidature'}
          </button>
          <button className="secondary" disabled={busy !== null} onClick={() => generateEmail('relance')}>
            {busy === 'email:relance' ? (<><span className="spin" style={{ borderTopColor: '#57606a' }} />Rédaction…</>) : '🔁 Email de relance'}
          </button>
        </div>
        {emailDraft && (
          <div className="desc" style={{ maxHeight: 'none' }}>
            <b>Objet : {emailDraft.objet}</b>
            {'\n\n'}{emailDraft.corps}
            {'\n'}
            <div className="actions-row" style={{ marginTop: 10 }}>
              <button
                className="secondary"
                onClick={() => {
                  navigator.clipboard.writeText(`Objet : ${emailDraft.objet}\n\n${emailDraft.corps}`)
                  showToast('Email copié dans le presse-papiers.')
                }}
              >
                Copier
              </button>
              <a href={`mailto:${encodeURIComponent(contacts.find((c) => c.email)?.email || '')}?subject=${encodeURIComponent(emailDraft.objet)}&body=${encodeURIComponent(emailDraft.corps)}`}>
                <button className="secondary">
                  Ouvrir dans mon client mail{contacts.find((c) => c.email) ? ` (→ ${contacts.find((c) => c.email).name})` : ''}
                </button>
              </a>
            </div>
          </div>
        )}

        <div className="section-title">Préparation d'entretien</div>
        <div className="actions-row" style={{ margin: '4px 0 8px' }}>
          <button
            className="primary"
            disabled={busy !== null}
            onClick={() => runAction('prep', async () => {
              const updated = await api.interviewPrep(offer.id)
              setOffer(updated)
              setPrep(updated.interview_prep || '')
            }, "Fiche d'entretien générée : pitch, points forts, questions probables, vigilances.")}
          >
            {busy === 'prep'
              ? (<><span className="spin" />Préparation en cours…</>)
              : (prep ? "Régénérer la fiche d'entretien" : "Préparer l'entretien avec Claude")}
          </button>
          {prep && (
            <button
              className="secondary"
              onClick={() => { navigator.clipboard.writeText(prep); showToast('Fiche copiée dans le presse-papiers.') }}
            >
              Copier la fiche
            </button>
          )}
        </div>
        <textarea
          rows={prep ? 14 : 3}
          placeholder="Pitch, points forts face à l'annonce, questions probables du recruteur, vigilances, questions à poser…"
          value={prep}
          onChange={(e) => setPrep(e.target.value)}
          onBlur={() => prep !== (offer.interview_prep || '') && patch({ interview_prep: prep }, 'Fiche enregistrée.')}
        />

        {offer.company && (
          <>
            <div className="section-title">Contacts chez {offer.company}</div>
            {contacts.length === 0 && <p className="hint" style={{ margin: '2px 0 6px' }}>Aucun contact enregistré pour cette entreprise.</p>}
            {contacts.map((c) => (
              <div key={c.id} className="actions-row" style={{ margin: '2px 0' }}>
                <span><b>{c.name}</b>{c.role ? ` · ${c.role}` : ''}</span>
                {c.email && <a href={`mailto:${c.email}`}>{c.email}</a>}
                {c.phone && <span className="hint">{c.phone}</span>}
                <button
                  className="fav" title="Supprimer ce contact" style={{ fontSize: 14 }}
                  onClick={async () => {
                    try { await api.deleteContact(c.id); loadContacts(offer.company) } catch (err) { showToast(err.message, true) }
                  }}
                >✕</button>
              </div>
            ))}
            {newContact === null ? (
              <button className="secondary" style={{ marginTop: 4 }} onClick={() => setNewContact({ name: '', role: '', email: '', phone: '' })}>
                + Ajouter un contact
              </button>
            ) : (
              <div className="actions-row" style={{ marginTop: 6 }}>
                <input type="text" placeholder="Nom *" style={{ width: 140 }} value={newContact.name} onChange={(e) => setNewContact({ ...newContact, name: e.target.value })} />
                <input type="text" placeholder="Rôle" style={{ width: 130 }} value={newContact.role} onChange={(e) => setNewContact({ ...newContact, role: e.target.value })} />
                <input type="text" placeholder="Email" style={{ width: 180 }} value={newContact.email} onChange={(e) => setNewContact({ ...newContact, email: e.target.value })} />
                <input type="text" placeholder="Téléphone" style={{ width: 120 }} value={newContact.phone} onChange={(e) => setNewContact({ ...newContact, phone: e.target.value })} />
                <button
                  className="primary"
                  onClick={async () => {
                    try {
                      await api.addContact({ company: offer.company, ...newContact })
                      setNewContact(null)
                      loadContacts(offer.company)
                      showToast('Contact ajouté.')
                    } catch (err) { showToast(err.message, true) }
                  }}
                >OK</button>
                <button className="secondary" onClick={() => setNewContact(null)}>Annuler</button>
              </div>
            )}
          </>
        )}

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
            <button
              className="fav" title="Supprimer cet entretien" style={{ fontSize: 14 }}
              onClick={async () => {
                try { setOffer(await api.deleteInterview(offer.id, i)) } catch (err) { showToast(err.message, true) }
              }}
            >✕</button>
          </div>
        ))}
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
                  setOffer(await api.addInterview(offer.id, {
                    date: `${newInterview.date}T${newInterview.heure || '10:00'}:00`,
                    format: newInterview.format,
                    interlocuteur: newInterview.interlocuteur,
                  }))
                  setNewInterview(null)
                  showToast('Entretien noté — il apparaîtra sur le tableau de bord.')
                } catch (err) { showToast(err.message, true) }
              }}
            >OK</button>
            <button className="secondary" onClick={() => setNewInterview(null)}>Annuler</button>
          </div>
        )}

        <div className="section-title">Prochaine action</div>
        <div className="actions-row" style={{ margin: '4px 0 8px' }}>
          <input
            type="date"
            value={offer.next_action_date ? offer.next_action_date.slice(0, 10) : ''}
            onChange={(e) => patch(
              { next_action_date: e.target.value || null },
              e.target.value ? 'Action planifiée.' : 'Action effacée.',
            )}
          />
          <input
            type="text"
            style={{ flex: 1, minWidth: 200 }}
            placeholder="ex. Relancer par email, préparer l'entretien…"
            value={actionNote}
            onChange={(e) => setActionNote(e.target.value)}
            onBlur={() => actionNote !== (offer.next_action_note || '') && patch({ next_action_note: actionNote || null })}
          />
          {offer.next_action_date && (
            <button
              className="secondary"
              onClick={() => { setActionNote(''); patch({ next_action_date: null, next_action_note: null }, 'Action marquée faite.') }}
            >
              Fait ✓
            </button>
          )}
        </div>

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
