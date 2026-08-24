import { Fragment, useEffect, useRef, useState } from 'react'
import { api, formatDate } from '../api.js'
import { useToast } from '../App.jsx'

function TagEditor({ values, onChange, placeholder }) {
  const [input, setInput] = useState('')
  const add = () => {
    const v = input.trim()
    if (v && !values.includes(v)) onChange([...values, v])
    setInput('')
  }
  return (
    <div className="tag-editor">
      {values.map((v) => (
        <span className="tag" key={v}>
          {v}
          <button onClick={() => onChange(values.filter((x) => x !== v))}>✕</button>
        </span>
      ))}
      <input
        type="text"
        value={input}
        placeholder={placeholder}
        onChange={(e) => setInput(e.target.value)}
        onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); add() } }}
        onBlur={add}
      />
    </div>
  )
}

const WEIGHT_FIELDS = [
  ['titre', 'Adéquation du poste', 40],
  ['competences', 'Compétences du CV', 25],
  ['seniorite', 'Niveau / séniorité', 10],
  ['localisation', 'Localisation', 15],
  ['contrat', 'Contrat', 5],
  ['secteur', 'Secteur', 5],
]

export default function ProfilePage() {
  const [profile, setProfile] = useState(null)
  const [saving, setSaving] = useState(false)
  const [showCv, setShowCv] = useState(false)
  const fileRef = useRef(null)
  const showToast = useToast()

  useEffect(() => {
    api.profile().then(setProfile).catch((err) => showToast(err.message, true))
  }, [showToast])

  if (!profile) return <p>Chargement…</p>

  const set = (key, value) => setProfile((p) => ({ ...p, [key]: value }))

  const save = async () => {
    setSaving(true)
    try {
      const body = {
        letter_template: profile.letter_template,
        target_titles: profile.target_titles,
        skills: profile.skills,
        location_label: profile.location_label,
        location_keywords: profile.location_keywords,
        radius_km: Number(profile.radius_km) || 40,
        remote_ok: profile.remote_ok,
        contracts: profile.contracts,
        excluded_keywords: profile.excluded_keywords,
        sector_bonus: profile.sector_bonus,
        scan_hour: profile.scan_hour,
        scoring_weights: profile.scoring_weights || null,
      }
      setProfile(await api.updateProfile(body))
      showToast('Profil enregistré — les scores des offres ont été recalculés.')
    } catch (err) {
      showToast(err.message, true)
    } finally {
      setSaving(false)
    }
  }

  const uploadCv = async (file) => {
    if (!file) return
    try {
      setProfile(await api.uploadCv(file))
      showToast('CV importé : texte extrait, compétences détectées et scores recalculés.')
    } catch (err) {
      showToast(`Import impossible : ${err.message}`, true)
    }
  }

  const toggleContract = (label) => {
    const has = profile.contracts.includes(label)
    set('contracts', has ? profile.contracts.filter((c) => c !== label) : [...profile.contracts, label])
  }

  return (
    <div>
      <h1>Profil & CV</h1>
      <p className="page-sub">C'est sur cette base que les offres sont classées.</p>

      <div className="card">
        <h2>CV</h2>
        <p className="hint" style={{ marginTop: 0 }}>
          Fichier actuel : <b>{profile.cv_filename || 'aucun'}</b>
          {profile.cv_updated_at && ` (importé le ${formatDate(profile.cv_updated_at)})`}
          {' · '}{profile.skills?.length || 0} compétence(s) détectée(s)
        </p>
        <div className="actions-row" style={{ margin: '6px 0' }}>
          <input
            ref={fileRef}
            type="file"
            accept=".pdf,.docx,.txt"
            style={{ display: 'none' }}
            onChange={(e) => uploadCv(e.target.files[0])}
          />
          <button className="primary" onClick={() => fileRef.current.click()}>
            Importer un nouveau CV (PDF / DOCX / TXT)
          </button>
          <button className="secondary" onClick={() => setShowCv(!showCv)}>
            {showCv ? 'Masquer le texte extrait' : 'Voir le texte extrait'}
          </button>
        </div>
        {showCv && <div className="desc" style={{ maxHeight: 260 }}>{profile.cv_text}</div>}
      </div>

      <div className="card">
        <h2>Compétences prises en compte dans le score</h2>
        <TagEditor values={profile.skills || []} onChange={(v) => set('skills', v)} placeholder="Ajouter une compétence…" />
      </div>

      <div className="card">
        <h2>Postes recherchés (score maximal)</h2>
        <p className="hint" style={{ marginTop: 0 }}>
          Les offres dont le titre correspond à l'un de ces intitulés obtiennent la note maximale d'adéquation.
        </p>
        <TagEditor values={profile.target_titles || []} onChange={(v) => set('target_titles', v)} placeholder="Ajouter un intitulé…" />
      </div>

      <div className="card">
        <h2>Critères de recherche</h2>
        <div className="form-grid">
          <label>Zone de recherche</label>
          <input type="text" value={profile.location_label} onChange={(e) => set('location_label', e.target.value)} />

          <label>Villes / mots-clés de zone</label>
          <TagEditor values={profile.location_keywords || []} onChange={(v) => set('location_keywords', v)} placeholder="Ajouter une ville…" />

          <label>Rayon (km)</label>
          <input type="number" min="5" max="200" value={profile.radius_km} onChange={(e) => set('radius_km', e.target.value)} style={{ width: 100 }} />

          <label>Full remote accepté</label>
          <input type="checkbox" checked={profile.remote_ok} onChange={(e) => set('remote_ok', e.target.checked)} />

          <label>Contrats</label>
          <div>
            {['CDI', 'Freelance / Portage', 'CDD', 'Intérim / Mission'].map((c) => (
              <label key={c} style={{ marginRight: 16 }}>
                <input type="checkbox" checked={profile.contracts.includes(c)} onChange={() => toggleContract(c)} /> {c}
              </label>
            ))}
          </div>

          <label>Secteurs bonus (déjà pratiqués)</label>
          <TagEditor values={profile.sector_bonus || []} onChange={(v) => set('sector_bonus', v)} placeholder="Ajouter un secteur…" />

          <label>Mots-clés exclus</label>
          <TagEditor values={profile.excluded_keywords || []} onChange={(v) => set('excluded_keywords', v)} placeholder="ex. une entreprise à éviter…" />

          <label>Heure du scan quotidien</label>
          <input type="time" value={profile.scan_hour} onChange={(e) => set('scan_hour', e.target.value)} style={{ width: 120 }} />
        </div>
      </div>

      <div className="card">
        <h2>Pondérations du score</h2>
        <p className="hint" style={{ marginTop: 0 }}>
          Le poids de chaque critère dans le classement. Le total est libre : le score est
          toujours ramené sur 100. Enregistrer recalcule toutes les offres.
        </p>
        <div className="form-grid" style={{ maxWidth: 480 }}>
          {WEIGHT_FIELDS.map(([key, label, def]) => {
            const weights = profile.scoring_weights || {}
            const value = weights[key] ?? def
            return (
              <Fragment key={key}>
                <label>{label}</label>
                <div>
                  <input
                    type="number" min="0" max="100" value={value} style={{ width: 80 }}
                    onChange={(e) => set('scoring_weights', {
                      ...Object.fromEntries(WEIGHT_FIELDS.map(([k, , d]) => [k, weights[k] ?? d])),
                      [key]: Math.max(0, Number(e.target.value) || 0),
                    })}
                  />
                  <span className="hint" style={{ marginLeft: 8 }}>défaut : {def}</span>
                </div>
              </Fragment>
            )
          })}
        </div>
        <p className="hint">
          Total actuel :{' '}
          <b>{WEIGHT_FIELDS.reduce((sum, [k, , d]) => sum + ((profile.scoring_weights || {})[k] ?? d), 0)}</b>
          {' '}· <button className="secondary" style={{ padding: '3px 10px', fontSize: 12 }}
            onClick={() => set('scoring_weights', null)}>Revenir aux défauts</button>
        </p>
      </div>

      <div className="card">
        <h2>Lettre de motivation type</h2>
        <p className="hint" style={{ marginTop: 0 }}>
          Base utilisée par Claude pour générer une lettre adaptée à chaque offre.
        </p>
        <textarea rows={14} value={profile.letter_template} onChange={(e) => set('letter_template', e.target.value)} />
      </div>

      <div className="actions-row">
        <button className="primary" onClick={save} disabled={saving}>
          {saving ? (<><span className="spin" />Enregistrement…</>) : 'Enregistrer le profil (et recalculer les scores)'}
        </button>
      </div>
    </div>
  )
}
