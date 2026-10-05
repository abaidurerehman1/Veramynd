import { useMemo } from 'react'

export type TrendPoint = { label: string; unit: number; value: number }

type Props = {
  title: string
  total: number
  percent: number
  percentLabel: string
  points: TrendPoint[]
}

// Card space is drawn in reference pixels (785 × 585) and scaled by CSS.
const W = 785
const H = 585
const STRIPE = 6.6 // stripe pitch
const TOP = 240 // y of the highest value
const LOW = 412 // y of the lowest value

const LOW_C: [number, number, number] = [143, 230, 246]
const MID_C: [number, number, number] = [79, 124, 238]
const HIGH_C: [number, number, number] = [44, 70, 184]

function mix(a: number[], b: number[], t: number) {
  return a.map((v, i) => Math.round(v + (b[i] - v) * t))
}

/** Level colour in landing tones: cyan (low) → blue (mid) → deep blue (high). */
function levelColor(t: number) {
  const c = t < 0.5 ? mix(LOW_C, MID_C, t / 0.5) : mix(MID_C, HIGH_C, (t - 0.5) / 0.5)
  return `rgb(${c[0]}, ${c[1]}, ${c[2]})`
}

/** Smooth per-lesson values into one value per stripe (cosine interpolation + light blur). */
function sampleWave(values: number[], count: number) {
  if (values.length === 0) return Array(count).fill(0)
  if (values.length === 1) return Array(count).fill(values[0])
  const raw = Array.from({ length: count }, (_, i) => {
    const pos = (i / (count - 1)) * (values.length - 1)
    const i0 = Math.floor(pos)
    const i1 = Math.min(values.length - 1, i0 + 1)
    const t = (1 - Math.cos((pos - i0) * Math.PI)) / 2
    return values[i0] * (1 - t) + values[i1] * t
  })
  // Wide blur: the design shows a calm wave with a few humps, not every lesson-to-lesson swing.
  const radius = Math.max(4, Math.round(count / 9))
  return raw.map((_, i) => {
    let sum = 0
    let weight = 0
    for (let k = -radius; k <= radius; k++) {
      const j = Math.min(count - 1, Math.max(0, i + k))
      const w = Math.exp(-(k * k) / (2 * (radius / 2) ** 2))
      sum += raw[j] * w
      weight += w
    }
    return sum / weight
  })
}

function niceCount(n: number) {
  return n >= 1000 ? `${Math.round(n / 100) / 10}k` : String(Math.round(n))
}

export function TrendCard({ title, total, percent, percentLabel, points }: Props) {
  const chart = useMemo(() => {
    const values = points.map((p) => p.value)
    const min = values.length ? Math.min(...values) : 0
    const max = values.length ? Math.max(...values) : 1
    const span = Math.max(1, max - min)
    const count = Math.floor(W / STRIPE) + 1
    const wave = sampleWave(values, count)
    // Height and colour use the smoothed curve's own range so the wave fills the card.
    const waveMin = Math.min(...wave)
    const waveSpan = Math.max(1e-6, Math.max(...wave) - waveMin)
    const stripes = wave.map((v, i) => {
      const t = (v - waveMin) / waveSpan
      return { x: 2 + i * STRIPE, y: LOW - t * (LOW - TOP), color: levelColor(t) }
    })
    const area =
      `M0 ${H} L0 ${stripes[0]?.y ?? LOW} ` +
      stripes.map((s) => `L${s.x.toFixed(1)} ${s.y.toFixed(1)}`).join(' ') +
      ` L${W} ${stripes[stripes.length - 1]?.y ?? LOW} L${W} ${H} Z`
    // Legend thresholds: lower and upper thirds of the observed range.
    const lowCut = min + span / 3
    const highCut = min + (2 * span) / 3
    const mid = (lowCut + highCut) / 2
    return { stripes, area, lowCut, highCut, mid }
  }, [points])

  const units = useMemo(() => {
    const seen: number[] = []
    points.forEach((p) => {
      if (!seen.includes(p.unit)) seen.push(p.unit)
    })
    return seen
  }, [points])

  return (
    <section className="vd-card vd-trend" aria-label={title}>
      <svg className="vd-trend__chart" viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" aria-hidden="true">
        <defs>
          <linearGradient id="vd-trend-fill" x1="0" y1="0" x2="1" y2="0">
            {chart.stripes
              .filter((_, i) => i % 4 === 0)
              .map((s) => (
                <stop key={s.x} offset={`${(s.x / W) * 100}%`} stopColor={s.color} />
              ))}
          </linearGradient>
          <linearGradient id="vd-trend-fade" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#fff" stopOpacity="1" />
            <stop offset="100%" stopColor="#fff" stopOpacity="0.62" />
          </linearGradient>
          <mask id="vd-trend-mask">
            <rect width={W} height={H} fill="url(#vd-trend-fade)" />
          </mask>
        </defs>
        <g mask="url(#vd-trend-mask)">
          <path d={chart.area} fill="url(#vd-trend-fill)" opacity="0.12" />
          {chart.stripes.map((s) => (
            <line key={s.x} x1={s.x} x2={s.x} y1={s.y} y2={H} stroke={s.color} strokeWidth="2.2" />
          ))}
        </g>
      </svg>

      <header className="vd-trend__head">
        <h2 className="vd-trend__title">{title}</h2>
        <span className="vd-trend__pct" title={percentLabel}>
          {percent}%
        </span>
      </header>
      <div className="vd-trend__row">
        <strong className="vd-trend__total">{total.toLocaleString()}</strong>
        <ul className="vd-legend" aria-label="Aligned standards per lesson">
          <li>
            <i className="pink" />
            &lt;{niceCount(chart.lowCut)}
          </li>
          <li>
            <i className="orange" />≈{niceCount(chart.mid)}
          </li>
          <li>
            <i className="green" />
            &gt;{niceCount(chart.highCut)}
          </li>
        </ul>
      </div>
      <ol className="vd-trend__units">
        {units.map((u) => (
          <li key={u}>Unit {u}</li>
        ))}
      </ol>
    </section>
  )
}

export default TrendCard
