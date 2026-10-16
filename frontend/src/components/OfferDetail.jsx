import { useEffect, useState } from 'react'
import { api, CHECKLIST_ETAPES, DEMO, downloadFile, formatDate, scoreColor, SOURCE_LABELS, STATUS_COLORS, STATUS_LABELS } from '../api.js'
import { useToast } from '../App.jsx'
import ContactsOffre from './ContactsOffre.jsx'
import EntretiensOffre from './EntretiensOffre.jsx'

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
  const [simulation, setSimulation] = useState(null)   // { echange: [], tour, reponse }
  const showToast = useToast()

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
      if (o.status === 'nouvelle') {
        api.updateOffer(o.id, { status: 'vue' }).then(setOffer).catch(() => {})
      }
    }).catch((err) => showToast(err.message, true))
  }, [offerId, showToast])

  // Simulation d'entretien jamais enregistrée (issue #15) : avertir avant de
  // la perdre plutôt que de la laisser disparaître sans prévenir, comme déjà
  // fait ailleurs dans ce fichier pour la suppression d'un entretien.
  const confirmerPerteSimulation = () =>
    !simulation?.echange?.length
    || window.confirm(
      "Tu as une simulation d'entretien en cours, non enregistrée — continuer l'effacera "
      + 'définitivement. Continuer ?'
    )
  const tryClose = () => { if (confirmerPerteSimulation()) onClose() }

  useEffect(() => {
    const onKey = (e) => { if (e.key === 'Escape') tryClose() }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [tryClose])

  if (!offer) {
    // Avant : `return null` — rien ne s'affichait pendant l'attente réseau,
    // au point de passer pour une appli cassée sur mobile/4G.
    return (
      <>
        <div className="drawer-backdrop" onClick={onClose} />
        <div className="drawer" role="dialog" aria-modal="true">
          <button className="close" aria-label="Fermer" onClick={onClose}>✕</button>
          <p className="hint">Chargement…</p>
        </div>
      </>
    )
  }

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
      <div className="drawer-backdrop" onClick={tryClose} />
      <div className="drawer" role="dialog" aria-modal="true">
        <button className="close" aria-label="Fermer" onClick={tryClose}>✕</button>

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
            // Couleur de bordure seulement — voir Offers.jsx, même correction de contraste.
            style={{ borderColor: STATUS_COLORS[offer.status], fontWeight: 700 }}
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
              }, "Description complète récupérée — score recalculé. L'avis de Claude, "
                 + 'qui portait sur l\'extrait, sera refait au prochain scan.')}
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

        {(offer.letter_versions || []).length > 0 && (
          <details style={{ margin: '6px 0 4px' }}>
            <summary className="hint" style={{ cursor: 'pointer' }}>
              Versions précédentes de la lettre ({offer.letter_versions.length})
            </summary>
            {offer.letter_versions.map((v, i) => (
              <div key={i} className="card" style={{ padding: 10, marginTop: 6 }}>
                <div className="actions-row" style={{ marginBottom: 6 }}>
                  <span className="hint">{formatDate(v.date)} · {v.par}</span>
                  <button className="secondary" style={{ padding: '2px 8px', fontSize: 13 }}
                    onClick={async () => {
                      try {
                        const maj = await api.restoreLetter(offer.id, i)
                        setOffer(maj)
                        setLetter(maj.cover_letter || '')
                        showToast('Version restaurée — la lettre en cours a été archivée.')
                      } catch (err) { showToast(err.message, true) }
                    }}>Restaurer</button>
                </div>
                <div className="desc" style={{ maxHeight: 160 }}>{v.texte}</div>
              </div>
            ))}
          </details>
        )}

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

        <div className="section-title">Simulation d'entretien</div>
        <p className="hint" style={{ margin: '2px 0 6px' }}>
          Claude joue le recruteur à partir de cette offre et de ton CV : il pose une question,
          tu réponds, il commente puis enchaîne.
        </p>
        <div className="actions-row" style={{ margin: '4px 0 8px' }}>
          <button
            className="primary" disabled={busy !== null}
            onClick={() => {
              if (!confirmerPerteSimulation()) return
              runAction('simu', async () => {
                const tour = await api.simulateInterview(offer.id, [])
                setSimulation({ echange: [], tour, reponse: '' })
              })
            }}
          >
            {busy === 'simu' ? (<><span className="spin" />Le recruteur réfléchit…</>) : (simulation ? '🔄 Recommencer la simulation' : '🎤 Démarrer la simulation')}
          </button>
          {simulation && (
            <button className="secondary" onClick={() => confirmerPerteSimulation() && setSimulation(null)}>Terminer</button>
          )}
        </div>
        {simulation?.tour && (
          <div className="card" style={{ padding: 12 }}>
            {simulation.tour.retour && (
              <div className="ai-box" style={{ marginTop: 0 }}>{simulation.tour.retour}</div>
            )}
            <p style={{ fontWeight: 700, marginBottom: 4 }}>{simulation.tour.question}</p>
            {simulation.tour.conseil && (
              <p className="hint" style={{ marginTop: 0 }}>💡 {simulation.tour.conseil}</p>
            )}
            <textarea
              rows={4} placeholder="Ta réponse…" value={simulation.reponse}
              onChange={(e) => setSimulation({ ...simulation, reponse: e.target.value })}
            />
            <div className="actions-row" style={{ marginTop: 6 }}>
              <button
                className="primary" disabled={busy !== null || !simulation.reponse.trim()}
                onClick={() => runAction('simu', async () => {
                  const echange = [
                    ...simulation.echange,
                    { question: simulation.tour.question, reponse: simulation.reponse },
                  ]
                  const tour = await api.simulateInterview(offer.id, echange)
                  setSimulation({ echange, tour, reponse: '' })
                })}
              >
                {busy === 'simu' ? (<><span className="spin" />Analyse…</>) : 'Répondre'}
              </button>
              <span className="hint">{simulation.echange.length} question(s) déjà traitée(s)</span>
            </div>
          </div>
        )}

        <div className="section-title">Adapter le CV à cette offre (ATS)</div>
        <div className="actions-row" style={{ margin: '4px 0 8px' }}>
          <button
            className="secondary" disabled={busy !== null}
            onClick={() => runAction('ats', async () => {
              setOffer(await api.reformulationAts(offer.id))
            }, 'Reformulation ATS générée : titre, accroche, puces et mots-clés.')}
          >
            {busy === 'ats'
              ? (<><span className="spin" style={{ borderTopColor: '#57606a' }} />Reformulation…</>)
              : (offer.ats_reformulation ? '📝 Régénérer la version ATS' : '📝 Reformuler mon CV pour cette offre')}
          </button>
          {offer.ats_reformulation && (
            <button className="secondary"
              onClick={() => { navigator.clipboard.writeText(offer.ats_reformulation); showToast('Reformulation copiée.') }}>
              Copier
            </button>
          )}
        </div>
        {offer.ats_reformulation && (
          <div className="desc" style={{ maxHeight: 320 }}>{offer.ats_reformulation}</div>
        )}

        <ContactsOffre company={offer.company} onContacts={setContacts} />

        <div className="section-title">Checklist de candidature</div>
        <div className="actions-row" style={{ margin: '4px 0 8px', flexWrap: 'wrap' }}>
          {Object.entries(CHECKLIST_ETAPES).map(([cle, libelle]) => {
            const coche = Boolean((offer.checklist || {})[cle])
            return (
              <label key={cle} className="chip" style={{ cursor: 'pointer', userSelect: 'none' }}>
                <input
                  type="checkbox" checked={coche} style={{ marginRight: 6 }}
                  onChange={() => patch({ checklist: { ...(offer.checklist || {}), [cle]: !coche } })}
                />
                {libelle}
              </label>
            )
          })}
        </div>

        <EntretiensOffre offer={offer} onOfferChange={setOffer} />

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
