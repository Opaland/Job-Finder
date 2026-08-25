import { useEffect, useRef, useState } from 'react'
import { api, DEMO, downloadFile } from '../api.js'
import { useToast } from '../App.jsx'

const KEY_HELP = {
  france_travail: 'Clés gratuites sur francetravail.io → FT_CLIENT_ID / FT_CLIENT_SECRET dans .env (voir README §3.1)',
  adzuna: 'Clés gratuites sur developer.adzuna.com → ADZUNA_APP_ID / ADZUNA_APP_KEY dans .env (README §3.2)',
  jsearch: 'Clé gratuite sur rapidapi.com (API JSearch) → RAPIDAPI_KEY dans .env (README §3.3) — couvre LinkedIn et Indeed',
  wttj: 'Sans clé. En cas d’erreur 4xx, mettre à jour WTTJ_ALGOLIA_API_KEY dans .env (README §3.4)',
  apec: 'Sans clé (service non officiel du site apec.fr) — peut casser si le site change',
  hellowork: 'Sans clé (lecture du site) — peut casser si le site change',
}

// Date locale au format AAAA-MM-JJ. toISOString() donnerait l'UTC : entre
// minuit et 2 h en été, la période par défaut serait décalée d'un jour.
const jourISO = (decalage = 0) => {
  const d = new Date(Date.now() + decalage * 86400000)
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

export default function Sources() {
  const [importing, setImporting] = useState(false)
  const csvRef = useRef(null)
  const [justifDu, setJustifDu] = useState(jourISO(-30))
  const [justifAu, setJustifAu] = useState(jourISO(0))
  const [data, setData] = useState(null)
  const [profile, setProfile] = useState(null)
  const [scans, setScans] = useState([])
  const [restoring, setRestoring] = useState(false)
  const restoreRef = useRef(null)
  const showToast = useToast()

  const load = async () => {
    try {
      const [src, prof, history] = await Promise.all([api.sources(), api.profile(), api.scans(8)])
      setData(src)
      setProfile(prof)
      setScans(history)
    } catch (err) {
      showToast(err.message, true)
    }
  }

  useEffect(() => { load() }, [])

  if (!data || !profile) return <p>Chargement…</p>

  const toggleSource = async (name, enabled) => {
    const sources_enabled = { ...(profile.sources_enabled || {}), [name]: enabled }
    try {
      setProfile(await api.updateProfile({ sources_enabled }))
      showToast(enabled ? 'Source activée.' : 'Source désactivée (elle ne sera plus scannée).')
      load()
    } catch (err) {
      showToast(err.message, true)
    }
  }

  const testEmail = async () => {
    try {
      await api.testEmail()
      showToast('Email de test envoyé — vérifie ta boîte.')
    } catch (err) {
      showToast(err.message, true)
    }
  }

  const sendDigest = async () => {
    try {
      await api.sendDigestEmail()
      showToast('Digest du jour envoyé par email.')
    } catch (err) {
      showToast(err.message, true)
    }
  }

  return (
    <div>
      <h1>Sources & réglages</h1>
      <p className="page-sub">État des connecteurs, de l'IA locale et de l'email quotidien.</p>

      <div className="card">
        <h2>Sources d'offres</h2>
        <table className="simple">
          <thead>
            <tr><th>Source</th><th>État</th><th>Dernier scan</th><th>Historique</th><th>Activée</th></tr>
          </thead>
          <tbody>
            {data.sources.map((s) => {
              const stats = s.last_stats
              return (
                <tr key={s.name}>
                  <td>
                    <b>{s.label}</b>
                    <div className="hint">{KEY_HELP[s.name]}</div>
                  </td>
                  <td>
                    {s.needs_key
                      ? (s.configured ? <span className="ok">Clé OK</span> : <span className="ko">Clé manquante</span>)
                      : <span className="ok">Sans clé</span>}
                  </td>
                  <td>
                    {stats ? (
                      <>
                        {stats.fetched ?? 0} récupérée(s), {stats.new ?? 0} nouvelle(s)
                        {stats.errors?.length > 0 && (
                          <div className="error-text">{stats.errors[0]}</div>
                        )}
                      </>
                    ) : <span className="hint">—</span>}
                  </td>
                  <td>
                    {s.history?.length ? (
                      <>
                        <div style={{ display: 'flex', gap: 2 }}>
                          {s.history.map((h, i) => (
                            <span
                              key={i}
                              title={`${h.date} — ${h.ok ? `OK (${h.new} nouvelle·s)` : 'erreur'}`}
                              style={{
                                width: 9, height: 16, borderRadius: 2,
                                background: h.ok ? '#0ca30c' : '#d03b3b',
                              }}
                            />
                          ))}
                        </div>
                        <span className="hint">
                          {s.history.filter((h) => !h.ok).length
                            ? `${s.history.filter((h) => !h.ok).length} erreur·s / ${s.history.length} scans`
                            : `${s.history.length} scans OK`}
                        </span>
                      </>
                    ) : <span className="hint">—</span>}
                  </td>
                  <td>
                    <input
                      type="checkbox"
                      checked={s.enabled}
                      onChange={(e) => toggleSource(s.name, e.target.checked)}
                    />
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
        <p className="hint">
          LinkedIn et Indeed interdisent la collecte directe : leurs offres arrivent via JSearch
          (Google for Jobs) et Adzuna. Prochain scan quotidien :{' '}
          {data.next_daily_scan ? new Date(data.next_daily_scan).toLocaleString('fr-FR') : '—'}.
        </p>
      </div>

      <div className="card">
        <h2>IA locale (session Claude Code)</h2>
        <p style={{ marginTop: 0 }}>
          {data.ai.available ? <span className="ok">Disponible</span> : <span className="warn">Indisponible</span>}
          {' — '}{data.ai.detail}
        </p>
        <p className="hint">
          Quand elle est disponible, l'IA affine le score des meilleures offres et génère les lettres
          de motivation adaptées. Sans elle, le classement par règles fonctionne normalement.
        </p>
      </div>

      <div className="card">
        <h2>Email quotidien</h2>
        <p style={{ marginTop: 0 }}>
          {data.email.configured
            ? <span className="ok">SMTP configuré</span>
            : <span className="warn">Non configuré</span>}
          {!data.email.configured && (
            <span className="hint"> — renseigne SMTP_USER, SMTP_PASSWORD et DIGEST_EMAIL_TO dans le fichier .env (README §4)</span>
          )}
        </p>
        <p className="hint" style={{ marginTop: 0 }}>
          Deux envois automatiques : le point du matin après le scan, et un rappel à 18 h la
          veille d'un entretien ou d'une action datée.
        </p>
        <div className="actions-row">
          <button className="secondary" onClick={testEmail}>Envoyer un email de test</button>
          <button className="secondary" onClick={sendDigest}>Envoyer le digest du jour maintenant</button>
          <button className="secondary" onClick={async () => {
            try {
              const r = await api.sendReminder()
              const total = r.entretiens.length + r.actions.length
              showToast(total === 0
                ? 'Rien de prévu demain : aucun rappel à envoyer.'
                : (r.envoye ? `Rappel envoyé (${total} échéance(s) demain).`
                            : `${total} échéance(s) demain — configure le SMTP pour recevoir le rappel.`))
            } catch (err) { showToast(err.message, true) }
          }}>Tester le rappel de la veille</button>
        </div>
      </div>

      <div className="card">
        <h2>Justificatif de recherche d'emploi</h2>
        <p className="hint" style={{ marginTop: 0 }}>
          PDF listant tes démarches (candidatures envoyées, relances, entretiens) sur la période
          choisie — à joindre à ton actualisation France Travail.
        </p>
        <div className="actions-row">
          <span className="hint">Du</span>
          <input type="date" value={justifDu} onChange={(e) => setJustifDu(e.target.value)} />
          <span className="hint">au</span>
          <input type="date" value={justifAu} onChange={(e) => setJustifAu(e.target.value)} />
          <button
            className="primary"
            onClick={() => {
              if (DEMO) {
                showToast("Justificatif disponible uniquement dans l'application locale (démo en ligne).", true)
                return
              }
              if (justifDu > justifAu) { showToast('La date de début doit précéder la date de fin.', true); return }
              downloadFile(api.justificatifUrl(justifDu, justifAu))
            }}
          >
            📄 Télécharger le justificatif
          </button>
        </div>
      </div>

      <div className="card">
        <h2>Import / export CSV</h2>
        <p className="hint" style={{ marginTop: 0 }}>
          Le CSV s'ouvre dans Excel ou LibreOffice (séparateur « ; »). À l'import, les offres
          déjà suivies sont reconnues et ignorées — rien n'est écrasé.
        </p>
        <div className="actions-row">
          <button
            className="secondary"
            onClick={() => {
              if (DEMO) { showToast("Export CSV disponible uniquement dans l'application locale (démo en ligne).", true); return }
              downloadFile(api.csvUrl())
            }}
          >
            ⬇️ Exporter en CSV
          </button>
          <button className="secondary" disabled={importing} onClick={() => csvRef.current?.click()}>
            {importing ? (<><span className="spin" style={{ borderTopColor: '#57606a' }} />Import…</>) : '⬆️ Importer un CSV'}
          </button>
          <input
            ref={csvRef} type="file" accept=".csv,text/csv" style={{ display: 'none' }}
            onChange={async (e) => {
              const fichier = e.target.files?.[0]
              e.target.value = ''
              if (!fichier) return
              setImporting(true)
              try {
                const r = await api.importCsv(fichier)
                showToast(`${r.ajoutees} offre(s) importée(s), ${r.doublons} doublon(s) ignoré(s).`)
              } catch (err) {
                showToast(err.message, true)
              } finally {
                setImporting(false)
              }
            }}
          />
        </div>
      </div>

      <div className="card">
        <h2>Sauvegarde</h2>
        <p className="hint" style={{ marginTop: 0 }}>
          Toutes tes données (offres, statuts, notes, lettres) vivent dans une base locale
          (<code>data/jobfinder.db</code>). Télécharge une copie régulièrement — pour restaurer,
          remplace le fichier par ta sauvegarde, application arrêtée.
        </p>
        <button
          className="secondary"
          onClick={() => {
            if (DEMO) {
              showToast("Sauvegarde disponible uniquement dans l'application locale (démo en ligne).", true)
              return
            }
            downloadFile('/api/backup')
          }}
        >
          💾 Télécharger une sauvegarde de la base
        </button>
        <input
          ref={restoreRef}
          type="file"
          accept=".db"
          style={{ display: 'none' }}
          onChange={async (e) => {
            const file = e.target.files[0]
            e.target.value = ''
            if (!file) return
            const ok = window.confirm(
              'Remplacer la base actuelle par cette sauvegarde ?\n\n' +
              'Une copie de sécurité de la base actuelle sera créée dans le dossier data/ avant le remplacement.',
            )
            if (!ok) return
            setRestoring(true)
            try {
              const result = await api.restore(file)
              showToast(`Base restaurée (${result.offers} offres) — copie de sécurité : ${result.safety_copy}`)
              load()
            } catch (err) {
              showToast(`Restauration impossible : ${err.message}`, true)
            } finally {
              setRestoring(false)
            }
          }}
        />
        <button
          className="secondary"
          style={{ marginLeft: 8 }}
          disabled={restoring}
          onClick={() => restoreRef.current.click()}
        >
          {restoring ? (<><span className="spin" style={{ borderTopColor: '#57606a' }} />Restauration…</>) : '↩️ Restaurer une sauvegarde…'}
        </button>
      </div>

      <div className="card">
        <h2>Historique des scans</h2>
        {scans.length === 0 && <p className="hint">Aucun scan pour l'instant.</p>}
        {scans.length > 0 && (
          <table className="simple">
            <thead>
              <tr><th>Date</th><th>Type</th><th>Nouvelles</th><th>Déjà connues</th><th>Erreurs</th></tr>
            </thead>
            <tbody>
              {scans.map((s) => (
                <tr key={s.id}>
                  <td>{new Date(s.started_at).toLocaleString('fr-FR')}</td>
                  <td>{s.trigger}</td>
                  <td>{s.new_count}</td>
                  <td>{s.seen_count}</td>
                  <td className={s.error_count ? 'warn' : ''}>{s.error_count}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}
