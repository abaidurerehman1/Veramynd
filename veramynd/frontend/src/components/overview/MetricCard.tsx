import type { ReactNode } from 'react'

type Props = {
  title: string
  icon: ReactNode
  value: number
  chip: string
  chipTone: 'up' | 'down' | 'warn'
  chipLabel: string
  sub: string
  percent: number
  percentLabel: string
}

export function MetricCard({ title, icon, value, chip, chipTone, chipLabel, sub, percent, percentLabel }: Props) {
  const pct = Math.max(0, Math.min(100, Math.round(percent)))
  return (
    <section className="vd-card vd-metric" aria-label={title}>
      <header className="vd-metric__head">
        <h3>{title}</h3>
        <span className="vd-metric__icon">{icon}</span>
      </header>
      <div className="vd-metric__value">
        <strong>{value.toLocaleString()}</strong>
        <span className={`vd-chip ${chipTone}`} title={chipLabel}>
          {chip}
        </span>
      </div>
      <p className="vd-metric__sub">{sub}</p>
      <div className="vd-metric__bar" title={percentLabel}>
        <div
          className="vd-progress"
          role="progressbar"
          aria-valuenow={pct}
          aria-valuemin={0}
          aria-valuemax={100}
          aria-label={percentLabel}
        >
          <span style={{ width: `${pct}%` }} />
        </div>
        <em>{pct}%</em>
      </div>
    </section>
  )
}

export default MetricCard
