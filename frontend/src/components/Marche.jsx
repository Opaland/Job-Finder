import { useEffect, useState } from 'react'
import { api } from '../api.js'

// Barre horizontale simple : lisible en clair comme en sombre, sans dépendance.
function Barre({ part, couleur }) {
  return (
    <div className="bar-bg" style={{ minWidth: 90 }}>
      <div className="bar-fill" style={{ width: `${Math.max(2, part)}%`, background: couleur }} />
    </div>
  )
}

export default function Marche() {
  const [skills, setSkills] = useState(null)
  const [erreur, setErreur] = useState(null)

  useEffect(() => {
    api.marketSkills().then(setSkills).catch((e) => setErreur(e.message))
  }, [])

  if (erreur) return <p className="error-text">Erreur : {erreur}</p>
  if (!skills) return <p>Chargement…</p>

  return (
    <div>
      <h1>Marché</h1>
      <p className="page-sub">
        Ce que disent les {skills.total_offres} offre(s) déjà collectées — calculé en local,
        sans aucune source externe.
      </p>

      {!skills.assez_de_donnees && (
        <div className="card">
          <p className="hint" style={{ margin: 0 }}>
            Pas encore assez d'offres pour un classement utile. Lance un scan : l'analyse
            s'affine à chaque collecte.
          </p>
        </div>
      )}

      {skills.manquantes.length > 0 && (
        <div className="card" style={{ borderColor: '#f0b37e' }}>
          <h2 style={{ color: '#bc4c00' }}>À travailler en priorité</h2>
          <p className="hint" style={{ marginTop: 0 }}>
            Demandé par les recruteurs, absent de ton CV — les meilleurs candidats à une
            formation ou à une mise en avant si tu l'as déjà pratiqué.
          </p>
          <table className="simple">
            <tbody>
              {skills.manquantes.map((c) => (
                <tr key={c.competence}>
                  <td style={{ textTransform: 'capitalize', fontWeight: 600 }}>{c.competence}</td>
                  <td style={{ width: 140 }}><Barre part={c.part} couleur="#bc4c00" /></td>
                  <td style={{ whiteSpace: 'nowrap' }}>{c.offres} offre(s) · {c.part} %</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <div className="card">
        <h2>Compétences les plus demandées</h2>
        <table className="simple">
          <tbody>
            {skills.competences.map((c) => (
              <tr key={c.competence}>
                <td style={{ textTransform: 'capitalize', fontWeight: 600 }}>
                  {c.competence}
                  {c.dans_le_cv && <span className="chip" style={{ marginLeft: 8 }}>dans ton CV</span>}
                </td>
                <td style={{ width: 140 }}>
                  <Barre part={c.part} couleur={c.dans_le_cv ? '#1a7f37' : '#57606a'} />
                </td>
                <td style={{ whiteSpace: 'nowrap' }}>{c.offres} · {c.part} %</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
