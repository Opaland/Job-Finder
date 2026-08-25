import { useEffect, useMemo, useRef, useState } from 'react'

// Palette de commandes (Ctrl+K) : navigation et actions au clavier, sans souris.
export default function Palette({ commandes, onClose }) {
  const [filtre, setFiltre] = useState('')
  const [index, setIndex] = useState(0)
  const champ = useRef(null)

  const visibles = useMemo(() => {
    const recherche = filtre.trim().toLowerCase()
    if (!recherche) return commandes
    return commandes.filter((c) => c.libelle.toLowerCase().includes(recherche))
  }, [commandes, filtre])

  useEffect(() => { champ.current?.focus() }, [])
  useEffect(() => { setIndex(0) }, [filtre])

  const lancer = (commande) => {
    onClose()
    commande?.action()
  }

  return (
    <>
      <div className="drawer-backdrop" onClick={onClose} />
      <div className="palette" role="dialog" aria-label="Palette de commandes">
        <input
          ref={champ}
          type="text"
          placeholder="Aller à… ou lancer une action (Échap pour fermer)"
          value={filtre}
          onChange={(e) => setFiltre(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'ArrowDown') { e.preventDefault(); setIndex((i) => Math.min(i + 1, visibles.length - 1)) }
            if (e.key === 'ArrowUp') { e.preventDefault(); setIndex((i) => Math.max(i - 1, 0)) }
            if (e.key === 'Enter') { e.preventDefault(); lancer(visibles[index]) }
          }}
        />
        <div className="palette-liste">
          {visibles.length === 0 && <div className="hint" style={{ padding: 10 }}>Aucune commande.</div>}
          {visibles.map((c, i) => (
            <button
              key={c.id}
              className={`palette-item ${i === index ? 'actif' : ''}`}
              onMouseEnter={() => setIndex(i)}
              onClick={() => lancer(c)}
            >
              <span>{c.libelle}</span>
              {c.raccourci && <kbd>{c.raccourci}</kbd>}
            </button>
          ))}
        </div>
      </div>
    </>
  )
}
