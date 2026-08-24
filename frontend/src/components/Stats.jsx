import { useEffect, useRef, useState } from 'react'
import { api, DEMO } from '../api.js'
import { useToast } from '../App.jsx'

// Palette dataviz validée (une seule teinte : magnitude → bleu séquentiel).
// Les pas sombres viennent de la même palette, choisis pour la surface sombre.
function pal() {
  const dark = typeof document !== 'undefined' && document.documentElement.dataset.theme === 'dark'
  return dark
    ? { BLUE: '#3987e5', INK_MUTED: '#8b949e', INK2: '#c3c2b7', GRID: '#30363d', BASELINE: '#484f58', RING: '#161b22' }
    : { BLUE: '#2a78d6', INK_MUTED: '#898781', INK2: '#52514e', GRID: '#e1e0d9', BASELINE: '#c3c2b7', RING: '#ffffff' }
}

function Tooltip({ tip }) {
  if (!tip) return null
  return (
    <div
      style={{
        position: 'fixed', left: tip.x + 12, top: tip.y + 12, zIndex: 90,
        background: '#10192b', color: '#fff', borderRadius: 8, padding: '6px 10px',
        fontSize: 12.5, pointerEvents: 'none', boxShadow: '0 4px 16px rgba(0,0,0,.3)',
      }}
    >
      {tip.text}
    </div>
  )
}

// Barre horizontale : extrémité arrondie 4px côté donnée, carrée à la base.
function hbarPath(x, y, width, height) {
  const r = Math.min(4, width)
  return `M ${x} ${y} h ${Math.max(0, width - r)} a ${r} ${r} 0 0 1 ${r} ${r} v ${height - 2 * r} a ${r} ${r} 0 0 1 -${r} ${r} h -${Math.max(0, width - r)} Z`
}

function colPath(x, y, width, height) {
  const r = Math.min(4, height)
  return `M ${x} ${y + height} v -${Math.max(0, height - r)} a ${r} ${r} 0 0 1 ${r} -${r} h ${width - 2 * r} a ${r} ${r} 0 0 1 ${r} ${r} v ${Math.max(0, height - r)} Z`
}

function HBarChart({ items, onHover }) {
  const { BLUE, INK_MUTED, INK2, GRID, BASELINE, RING } = pal()
  const max = Math.max(1, ...items.map((d) => d.count))
  const rowH = 30
  const barH = 18
  const labelW = 170
  const valueW = 36
  const width = 560
  const plotW = width - labelW - valueW
  const height = items.length * rowH
  return (
    <svg width="100%" viewBox={`0 0 ${width} ${height}`} role="img">
      {items.map((d, i) => {
        const bw = (d.count / max) * plotW
        const y = i * rowH + (rowH - barH) / 2
        return (
          <g
            key={d.label}
            onMouseMove={(e) => onHover({ x: e.clientX, y: e.clientY, text: `${d.label} : ${d.count} offre${d.count > 1 ? 's' : ''}` })}
            onMouseLeave={() => onHover(null)}
          >
            <text x={labelW - 8} y={y + barH / 2 + 4} textAnchor="end" fontSize="12.5" fill={INK2}>
              {d.label}
            </text>
            {d.count > 0 ? (
              <path d={hbarPath(labelW, y, Math.max(bw, 4), barH)} fill={BLUE} />
            ) : (
              <line x1={labelW} y1={y + barH / 2} x2={labelW + 4} y2={y + barH / 2} stroke={BASELINE} strokeWidth="2" />
            )}
            <text x={labelW + Math.max(bw, 4) + 6} y={y + barH / 2 + 4} fontSize="12" fill={INK2} style={{ fontVariantNumeric: 'tabular-nums' }}>
              {d.count}
            </text>
          </g>
        )
      })}
      <line x1={labelW} y1={0} x2={labelW} y2={height} stroke={BASELINE} strokeWidth="1" />
    </svg>
  )
}

function Histogram({ bins, onHover }) {
  const { BLUE, INK_MUTED, INK2, GRID, BASELINE, RING } = pal()
  const max = Math.max(1, ...bins.map((b) => b.count))
  const width = 560
  const height = 180
  const padB = 24
  const padL = 30
  const plotW = width - padL - 8
  const plotH = height - padB - 12
  const slot = plotW / bins.length
  const barW = Math.min(24, slot - 2)
  const maxIndex = bins.findIndex((b) => b.count === max)
  const ticks = [0, Math.ceil(max / 2), max]
  return (
    <svg width="100%" viewBox={`0 0 ${width} ${height}`} role="img">
      {ticks.map((t) => {
        const y = 12 + plotH - (t / max) * plotH
        return (
          <g key={t}>
            <line x1={padL} y1={y} x2={width - 8} y2={y} stroke={GRID} strokeWidth="1" />
            <text x={padL - 6} y={y + 4} textAnchor="end" fontSize="11" fill={INK_MUTED} style={{ fontVariantNumeric: 'tabular-nums' }}>{t}</text>
          </g>
        )
      })}
      {bins.map((b, i) => {
        const h = (b.count / max) * plotH
        const x = padL + i * slot + (slot - barW) / 2
        const y = 12 + plotH - h
        return (
          <g
            key={b.label}
            onMouseMove={(e) => onHover({ x: e.clientX, y: e.clientY, text: `Score ${b.label} : ${b.count} offre${b.count > 1 ? 's' : ''}` })}
            onMouseLeave={() => onHover(null)}
          >
            <rect x={padL + i * slot} y={12} width={slot} height={plotH} fill="transparent" />
            {b.count > 0 && <path d={colPath(x, y, barW, Math.max(h, 4))} fill={BLUE} />}
            {i === maxIndex && b.count > 0 && (
              <text x={x + barW / 2} y={y - 5} textAnchor="middle" fontSize="11.5" fill={INK2} style={{ fontVariantNumeric: 'tabular-nums' }}>{b.count}</text>
            )}
            <text x={padL + i * slot + slot / 2} y={height - 6} textAnchor="middle" fontSize="10.5" fill={INK_MUTED}>
              {b.label}
            </text>
          </g>
        )
      })}
      <line x1={padL} y1={12 + plotH} x2={width - 8} y2={12 + plotH} stroke={BASELINE} strokeWidth="1" />
    </svg>
  )
}

function ActivityChart({ days, onHover }) {
  const { BLUE, INK_MUTED, INK2, GRID, BASELINE, RING } = pal()
  const max = Math.max(1, ...days.map((d) => d.count))
  const width = 560
  const height = 170
  const padL = 30
  const padB = 22
  const plotW = width - padL - 12
  const plotH = height - padB - 14
  const [hoverI, setHoverI] = useState(null)
  const px = (i) => padL + (i / Math.max(1, days.length - 1)) * plotW
  const py = (c) => 14 + plotH - (c / max) * plotH
  const line = days.map((d, i) => `${i === 0 ? 'M' : 'L'} ${px(i).toFixed(1)} ${py(d.count).toFixed(1)}`).join(' ')
  const area = `${line} L ${px(days.length - 1)} ${14 + plotH} L ${padL} ${14 + plotH} Z`
  const fmt = (iso) => new Date(iso + 'T00:00:00').toLocaleDateString('fr-FR', { day: '2-digit', month: 'short' })
  const ticks = [0, Math.ceil(max / 2), max]
  return (
    <svg
      width="100%" viewBox={`0 0 ${width} ${height}`} role="img"
      onMouseLeave={() => { setHoverI(null); onHover(null) }}
      onMouseMove={(e) => {
        const rect = e.currentTarget.getBoundingClientRect()
        const sx = ((e.clientX - rect.left) / rect.width) * width
        const i = Math.max(0, Math.min(days.length - 1, Math.round(((sx - padL) / plotW) * (days.length - 1))))
        setHoverI(i)
        onHover({ x: e.clientX, y: e.clientY, text: `${fmt(days[i].date)} : ${days[i].count} nouvelle${days[i].count > 1 ? 's' : ''} offre${days[i].count > 1 ? 's' : ''}` })
      }}
    >
      {ticks.map((t) => (
        <g key={t}>
          <line x1={padL} y1={py(t)} x2={width - 12} y2={py(t)} stroke={GRID} strokeWidth="1" />
          <text x={padL - 6} y={py(t) + 4} textAnchor="end" fontSize="11" fill={INK_MUTED} style={{ fontVariantNumeric: 'tabular-nums' }}>{t}</text>
        </g>
      ))}
      <path d={area} fill={BLUE} opacity="0.1" />
      <path d={line} fill="none" stroke={BLUE} strokeWidth="2" strokeLinejoin="round" strokeLinecap="round" />
      {hoverI != null && (
        <>
          <line x1={px(hoverI)} y1={14} x2={px(hoverI)} y2={14 + plotH} stroke={BASELINE} strokeWidth="1" />
          <circle cx={px(hoverI)} cy={py(days[hoverI].count)} r="4" fill={BLUE} stroke={RING} strokeWidth="2" />
        </>
      )}
      <circle cx={px(days.length - 1)} cy={py(days[days.length - 1].count)} r="4" fill={BLUE} stroke={RING} strokeWidth="2" />
      <text x={padL} y={height - 4} fontSize="10.5" fill={INK_MUTED}>{fmt(days[0].date)}</text>
      <text x={width - 12} y={height - 4} textAnchor="end" fontSize="10.5" fill={INK_MUTED}>{fmt(days[days.length - 1].date)}</text>
      <line x1={padL} y1={14 + plotH} x2={width - 12} y2={14 + plotH} stroke={BASELINE} strokeWidth="1" />
    </svg>
  )
}

const STATUS_FR = {
  nouvelle: 'Nouvelles', vue: 'Vues', a_postuler: 'À postuler', postulee: 'Postulées',
  relancee: 'Relancées', entretien: 'Entretiens', refusee: 'Refusées', fermee: 'Fermées',
}

export default function Stats() {
  const { BLUE } = pal()
  const [data, setData] = useState(null)
  const [tip, setTip] = useState(null)
  const showToast = useToast()
  const loaded = useRef(false)

  useEffect(() => {
    if (loaded.current) return
    loaded.current = true
    api.stats().then(setData).catch((err) => showToast(err.message, true))
  }, [showToast])

  if (!data) return <p>Chargement…</p>
  const t = data.totals

  return (
    <div>
      <h1>Statistiques</h1>
      <p className="page-sub">Le pilotage de ta recherche, en chiffres.</p>

      <div className="cards-row">
        <div className="stat"><div className="value">{t.offers}</div><div className="label">Offres suivies</div></div>
        <div className="stat"><div className="value" style={{ color: BLUE }}>{t.new_7d}</div><div className="label">Nouvelles (7 jours)</div></div>
        <div className="stat"><div className="value">{t.avg_top20 ?? '—'}</div><div className="label">Score moyen du top 20</div></div>
        <div className="stat"><div className="value" style={{ color: '#9a6700' }}>{t.sent}</div><div className="label">Candidatures envoyées</div></div>
        <div className="stat"><div className="value" style={{ color: '#1a7f37' }}>{t.interviews}</div><div className="label">Entretiens</div></div>
        <div className="stat"><div className="value">{t.response_rate != null ? `${t.response_rate}%` : '—'}</div><div className="label">Taux de réponse</div></div>
      </div>

      <div className="card">
        <h2>Nouvelles offres collectées — 30 derniers jours</h2>
        <ActivityChart days={data.per_day} onHover={setTip} />
      </div>

      <div className="card">
        <h2>Pipeline par statut</h2>
        <HBarChart items={data.by_status.map((s) => ({ label: STATUS_FR[s.status] || s.status, count: s.count }))} onHover={setTip} />
      </div>

      <div className="card">
        <h2>Offres par source</h2>
        <HBarChart items={data.by_source.map((s) => ({ label: s.label, count: s.count }))} onHover={setTip} />
      </div>

      {data.companies?.length > 0 && (
        <div className="card">
          <h2>Réactivité des entreprises</h2>
          <p className="hint" style={{ marginTop: 0 }}>
            Calculée depuis l'historique de tes candidatures (une « réponse » = passage en entretien ou refus).
          </p>
          <table className="simple">
            <thead>
              <tr>
                <th>Entreprise</th><th>Candidatures</th><th>Réponses</th>
                <th>Délai moyen de réponse</th><th>En attente depuis</th>
              </tr>
            </thead>
            <tbody>
              {data.companies.map((c) => (
                <tr key={c.company}>
                  <td><b>{c.company}</b></td>
                  <td>{c.applications}</td>
                  <td>{c.responses}</td>
                  <td>{c.avg_response_days != null ? `${c.avg_response_days} j` : '—'}</td>
                  <td className={c.pending_days >= 7 ? 'warn' : ''}>
                    {c.pending_days != null ? `${c.pending_days} j` : '—'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <div className="card">
        <h2>Distribution des scores</h2>
        <p className="hint" style={{ marginTop: 0 }}>Plus la distribution penche à droite, plus la collecte est pertinente.</p>
        <Histogram bins={data.score_bins} onHover={setTip} />
      </div>

      <Tooltip tip={tip} />
    </div>
  )
}
