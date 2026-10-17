// Composant de chargement partagé (issue #48) — remplace les multiples
// `<p>Chargement…</p>` et `return null` ad hoc dispersés dans les vues.
export default function Chargement({ texte = 'Chargement…' }) {
  return (
    <p className="hint chargement">
      <span className="spin chargement-spin" />
      {texte}
    </p>
  )
}
