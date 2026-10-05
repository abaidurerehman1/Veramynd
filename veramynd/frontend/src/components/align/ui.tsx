import { useEffect, useState, type ReactNode } from 'react'
import { createPortal } from 'react-dom'
import { Link } from 'react-router-dom'
import { TopbarContent } from '../layout/TopbarSlot'
import { STATE_NAMES, gradeLabel, type Agg, type Decision, type RollUp } from './data'
import { COV_COLORS, band, formatDecisionDate } from './scale'

export function Kpi({
  label,
  value,
  unit,
  of,
  sub,
  accent,
}: {
  label: string
  value: ReactNode
  unit?: string
  of?: string
  sub: ReactNode
  accent?: boolean
}) {
  return (
    <div className={`kpi${accent ? ' kpi-accent' : ''}`}>
      <div className="k-label">{label}</div>
      <div className="k-val cell-num">
        {value}
        {unit ? <span className="unit">{unit}</span> : null}
        {of ? <span className="of">{of}</span> : null}
      </div>
      <div className="k-sub">{sub}</div>
    </div>
  )
}

/** Met / partial / gap stacked bar for one domain. */
export function StrandBar({
  name,
  m,
  p,
  g,
  onClick,
  current,
}: {
  name: string
  m: number
  p: number
  g: number
  onClick?: () => void
  current?: boolean
}) {
  const body = (
    <>
      <div className="strand-top">
        <span className="strand-name">
          {name}
          {onClick ? <span className="arrow">View standards →</span> : null}
        </span>
        <span className="strand-meta">
          {m}% met · {p}% partial · {g}% gap
        </span>
      </div>
      <div className="stack" aria-hidden="true">
        <span className="seg-met" style={{ width: `${m}%` }} />
        <span className="seg-partial" style={{ width: `${p}%` }} />
        <span className="seg-gap" style={{ width: `${g}%` }} />
      </div>
    </>
  )
  if (!onClick) return <div className="strand-row">{body}</div>
  return (
    <button type="button" className={`strand-row clickable${current ? ' current' : ''}`} onClick={onClick}>
      {body}
    </button>
  )
}

const ROLL_LABEL: Record<RollUp, string> = { met: 'Met', partial: 'Partial', gap: 'Gap' }

export function RollBadge({ status, fill }: { status: RollUp; fill?: boolean }) {
  // In tables a met standard reads "Full", as in the reference design.
  const label = fill && status === 'met' ? 'Full' : ROLL_LABEL[status]
  return (
    <span className={`badge ${fill ? 'fill' : 'roll'} ${status}`}>
      <span className="dot" />
      {label}
    </span>
  )
}

export function MatchBadge({ match }: { match: 'full' | 'partial' | 'none' }) {
  const cls = match === 'none' ? 'gap' : match
  return (
    <span className={`badge fill ${cls}`}>
      <span className="dot" />
      {match === 'full' ? 'Full' : match === 'partial' ? 'Partial' : 'None'}
    </span>
  )
}

export type Crumb = { label: string; onClick?: () => void }

export function Crumbs({ trail, here }: { trail: Crumb[]; here: string }) {
  return (
    <nav className="va-crumbs" aria-label="Breadcrumb">
      {trail.map((c) => (
        <span key={c.label} style={{ display: 'contents' }}>
          <button type="button" className="lnk" onClick={c.onClick}>
            {c.label}
          </button>
          <span className="sep">/</span>
        </span>
      ))}
      <span className="here">{here}</span>
    </nav>
  )
}

type TopbarProps = {
  trail: Crumb[]
  here: string
  /** The State select shows only on state and standard screens, as in the mockup. */
  states?: { value: string; onChange: (s: string) => void; options: string[] }
  grade: string
  gradeOptions: string[]
  onGrade: (g: string) => void
  exportHref: string
}

/** The Align topbar: clickable crumbs, then State, Grade and Export report. Rendered into the app topbar. */
export function AlignTopbar({ trail, here, states, grade, gradeOptions, onGrade, exportHref }: TopbarProps) {
  return (
    <TopbarContent>
      <div className="va va-topbar">
        <Crumbs trail={trail} here={here} />
        <div className="va-topbar-right">
          {states ? (
            <label className="ctrl">
              <span className="lbl">State</span>
              <select className="brand" value={states.value} onChange={(e) => states.onChange(e.target.value)}>
                {states.options.map((s) => (
                  <option key={s} value={s}>
                    {STATE_NAMES[s] ?? s}
                  </option>
                ))}
              </select>
            </label>
          ) : null}
          <label className="ctrl">
            <span className="lbl">Grade</span>
            <select className="brand" value={grade} onChange={(e) => onGrade(e.target.value)}>
              <option value="all">All grades{gradeOptions.length > 1 ? ` (${gradeOptions.map((g) => (g === 'K' ? 'K' : g)).join(', ')})` : ''}</option>
              {gradeOptions.map((g) => (
                <option key={g} value={g}>
                  {gradeLabel(g)}
                </option>
              ))}
            </select>
          </label>
          <Link className="btn" to={exportHref}>
            Export report
          </Link>
        </div>
      </div>
    </TopbarContent>
  )
}

type MapProps = {
  byState: Record<string, Agg>
  selected?: string | null
  onSelect: (state: string) => void
}

/** Choropleth of coverage by state; states without a project stay grey. */
export function UsMap({ byState, selected, onSelect }: MapProps) {
  const [geo, setGeo] = useState<{ viewBox: string; paths: Record<string, string> } | null>(null)
  const [tip, setTip] = useState<{ x: number; y: number; state: string } | null>(null)

  useEffect(() => {
    let cancelled = false
    void import('./usMapPaths').then((m) => {
      if (!cancelled) setGeo({ viewBox: m.US_MAP_VIEWBOX, paths: m.US_STATE_PATHS })
    })
    return () => {
      cancelled = true
    }
  }, [])

  if (!geo) return <div className="usmap" style={{ aspectRatio: '1028 / 746' }} aria-hidden="true" />

  const tipAgg = tip ? byState[tip.state] : null
  return (
    <>
      <svg className="usmap" viewBox={geo.viewBox} role="img" aria-label="United States coverage heat map">
        {Object.entries(geo.paths).map(([code, d]) => {
          if (code === 'DC') return <path key={code} d={d} className="state unmapped" aria-hidden="true" />
          const agg = byState[code]
          const cls = ['state', agg ? 'mapped' : 'unmapped', selected === code ? 'selected' : ''].join(' ')
          const label = agg
            ? `${STATE_NAMES[code]}, ${agg.coverage} percent coverage`
            : `${STATE_NAMES[code]}, not mapped yet`
          return (
            <path
              key={code}
              d={d}
              className={cls}
              style={agg ? { fill: COV_COLORS[band(agg.coverage)] } : undefined}
              tabIndex={agg ? 0 : -1}
              role={agg ? 'button' : undefined}
              aria-label={label}
              onClick={() => agg && onSelect(code)}
              onKeyDown={(e) => {
                if (agg && (e.key === 'Enter' || e.key === ' ')) {
                  e.preventDefault()
                  onSelect(code)
                }
              }}
              onMouseMove={(e) => setTip({ x: e.clientX, y: e.clientY, state: code })}
              onMouseLeave={() => setTip(null)}
            />
          )
        })}
      </svg>
      {tip
        ? createPortal(
            <div
              className="va-maptip"
              style={{
                left: tip.x > window.innerWidth - 240 ? tip.x - 234 : tip.x + 14,
                top: tip.y > window.innerHeight - 90 ? tip.y - 84 : tip.y + 14,
              }}
            >
              <div className="t-name">{STATE_NAMES[tip.state]}</div>
              {tipAgg ? (
                <>
                  <div>{tipAgg.coverage}% coverage</div>
                  <div className="t-detail">
                    {tipAgg.met} met · {tipAgg.partial} partial · {tipAgg.gap} gap
                  </div>
                </>
              ) : (
                <div className="t-detail">Not mapped yet: no project for this state</div>
              )}
            </div>,
            document.body,
          )
        : null}
    </>
  )
}

/** Verification state of one citation, with the SME actions. */
export function VerificationCell({
  decision,
  flagged,
  onDecide,
  busy,
}: {
  decision?: Decision
  flagged: boolean
  onDecide: (d: 'accepted' | 'rejected' | 'pending') => void
  busy?: boolean
}) {
  if (decision?.decision === 'accepted') {
    return (
      <>
        <span className="vbadge ok">Expert-verified</span>
        <div className="vmeta">
          {decision.reviewer ? `${decision.reviewer} · ` : ''}
          {formatDecisionDate(decision.decided_at)}
        </div>
        <div className="vact">
          <button type="button" className="vbtn" disabled={busy} onClick={() => onDecide('pending')}>
            Undo
          </button>
        </div>
      </>
    )
  }
  if (decision?.decision === 'rejected') {
    return (
      <>
        <span className="vbadge no">Rejected</span>
        <div className="vmeta">{decision.reviewer ? `By ${decision.reviewer}` : ''}</div>
        <div className="vact">
          <button type="button" className="vbtn" disabled={busy} onClick={() => onDecide('pending')}>
            Undo
          </button>
        </div>
      </>
    )
  }
  return (
    <>
      <span className={`vbadge ${flagged ? 'pend' : 'none'}`}>{flagged ? 'Pending review' : 'Not yet reviewed'}</span>
      <div className="vact">
        <button type="button" className="vbtn acc" disabled={busy} onClick={() => onDecide('accepted')}>
          Accept
        </button>
        <button type="button" className="vbtn" disabled={busy} onClick={() => onDecide('rejected')}>
          Reject
        </button>
      </div>
    </>
  )
}
