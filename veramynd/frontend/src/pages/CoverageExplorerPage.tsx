import { useMemo, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import type { AlignmentRow } from '../api/types'
import {
  STATE_NAMES,
  aggregate,
  cleanQuote,
  gradeLabel,
  gradesOf,
  lessonName,
  pageRange,
  rememberGrade,
  shares,
  storedGrade,
  useAlignProjects,
  useProjectAlignments,
  useReviewDecisions,
  useReviewQueue,
  type Agg,
  type LeafStandard,
  type ProjectAlign,
  type RollUp,
} from '../components/align/data'
import { COV_COLORS, COV_TICKS } from '../components/align/scale'
import {
  AlignTopbar,
  Kpi,
  MatchBadge,
  RollBadge,
  StrandBar,
  UsMap,
  VerificationCell,
  type Crumb,
} from '../components/align/ui'
import '../components/align/align.css'

type Row = LeafStandard & { projectId: string; grade: string }
type Filter = 'all' | RollUp

function rowsOf(projects: ProjectAlign[]): Row[] {
  return projects.flatMap((p) => p.leaves.map((l) => ({ ...l, projectId: p.project.id, grade: p.grade })))
}

/** Domain-level met/partial/gap counts, keyed by domain label so frameworks can be combined. */
function byDomain(rows: Row[]) {
  const acc = new Map<string, { code: string; met: number; partial: number; gap: number }>()
  rows.forEach((r) => {
    const d = acc.get(r.domainLabel) ?? { code: r.domainCode, met: 0, partial: 0, gap: 0 }
    d[r.status] += 1
    acc.set(r.domainLabel, d)
  })
  return [...acc.entries()].map(([label, d]) => ({ label, ...d }))
}

function frameworksOf(projects: ProjectAlign[]) {
  return [...new Set(projects.map((p) => p.framework).filter(Boolean))].join(', ')
}

export function CoverageExplorerPage({ reloadKey = 0, projectId }: { reloadKey?: number; projectId: string }) {
  const { data, error } = useAlignProjects(reloadKey)
  const [params, setParams] = useSearchParams()
  const navigate = useNavigate()
  const grade = params.get('grade') || storedGrade()
  // Where a standard was opened from: the review queue or the Alignment page change its crumbs.
  const from = params.get('from')
  const state = params.get('state')
  const domain = params.get('domain')
  const std = params.get('std')
  const stdProject = params.get('pid')
  const [filter, setFilter] = useState<Filter>('all')

  const go = (next: Record<string, string | null>) => {
    const p = new URLSearchParams()
    const merged = { grade, state, domain, std, pid: stdProject, ...next }
    if (next.grade) rememberGrade(next.grade)
    Object.entries(merged).forEach(([k, v]) => {
      if (v && !(k === 'grade' && v === 'all')) p.set(k, v)
    })
    setParams(p)
    setFilter('all')
    window.scrollTo(0, 0)
  }

  const projects = useMemo(() => data ?? [], [data])
  const gradeOptions = useMemo(() => gradesOf(projects), [projects])
  const inGrade = useMemo(() => projects.filter((p) => grade === 'all' || p.grade === grade), [projects, grade])
  const mapped = useMemo(() => inGrade.filter((p) => p.state), [inGrade])

  const byState = useMemo(() => {
    const groups: Record<string, ProjectAlign[]> = {}
    mapped.forEach((p) => {
      ;(groups[p.state as string] ??= []).push(p)
    })
    return groups
  }, [mapped])
  const aggByState = useMemo(() => {
    const out: Record<string, Agg> = {}
    Object.entries(byState).forEach(([s, ps]) => {
      out[s] = aggregate(ps.flatMap((p) => p.leaves))
    })
    return out
  }, [byState])

  // ---- verification summary across every project ----
  const allIds = useMemo(() => projects.map((p) => p.project.id), [projects])
  const { decisions, available, error: decideError, decide } = useReviewDecisions(allIds)
  const { rows: queue } = useReviewQueue(allIds, reloadKey)
  const reviewRows = useMemo(() => queue ?? {}, [queue])

  const verification = useMemo(() => {
    const positive = projects.reduce((s, p) => s + p.leaves.reduce((t, l) => t + l.full + l.partial, 0), 0)
    let accepted = 0
    let pending = 0
    projects.forEach((p) => {
      const d = decisions[p.project.id] ?? {}
      accepted += Object.values(d).filter((x) => x.decision === 'accepted').length
      pending += (reviewRows[p.project.id] ?? []).filter((r) => !d[r.id]).length
    })
    return { positive, accepted, pending }
  }, [projects, decisions, reviewRows])

  // ---- current scope ----
  const stateProjects = state ? (byState[state] ?? []) : []
  const stateRows = rowsOf(stateProjects)
  const domainRows = domain ? stateRows.filter((r) => r.domainCode === domain || r.domainLabel === domain) : stateRows
  const domainName = domain ? (domainRows[0]?.domainLabel ?? domain) : null
  const stdRow = std ? stateRows.find((r) => r.code === std && (!stdProject || r.projectId === stdProject)) : undefined
  const screen: 'overview' | 'state' | 'standard' = stdRow ? 'standard' : state && stateProjects.length ? 'state' : 'overview'
  const exportProject = stdRow?.projectId ?? stateProjects[0]?.project.id ?? projectId

  const toOverview = () => go({ state: null, domain: null, std: null, pid: null })
  const trail: Crumb[] = []
  let here = 'National overview'
  if (screen === 'standard' && stdRow && from === 'review') {
    trail.push({ label: 'National overview', onClick: toOverview })
    trail.push({ label: 'Expert review queue', onClick: () => navigate(`/projects/${projectId}/review`) })
    here = stdRow.code
  } else if (screen === 'standard' && stdRow && from === 'alignment') {
    trail.push({ label: 'National overview', onClick: toOverview })
    trail.push({ label: 'Standards alignment', onClick: () => navigate(`/projects/${projectId}/alignment`) })
    here = stdRow.code
  } else if (screen !== 'overview' && state) {
    trail.push({ label: 'National overview', onClick: toOverview })
    here = STATE_NAMES[state]
    if (domainName) {
      trail.push({ label: STATE_NAMES[state], onClick: () => go({ domain: null, std: null, pid: null }) })
      here = domainName
    }
    if (stdRow) {
      if (domainName) trail.push({ label: domainName, onClick: () => go({ std: null, pid: null }) })
      else trail.push({ label: STATE_NAMES[state], onClick: () => go({ std: null, pid: null }) })
      here = stdRow.code
    }
  }

  return (
    <div className="va">
      <AlignTopbar
        trail={trail}
        here={here}
        states={
          screen !== 'overview' && state
            ? {
                value: state,
                options: Object.keys(byState).sort((a, b) => STATE_NAMES[a].localeCompare(STATE_NAMES[b])),
                onChange: (s) => go({ state: s, domain: null, std: null, pid: null }),
              }
            : undefined
        }
        grade={grade}
        gradeOptions={gradeOptions}
        onGrade={(g) => go({ grade: g, std: null, pid: null })}
        exportHref={`/projects/${exportProject}/exports`}
      />

      {error ? <div className="va-screen"><div className="va-error">Could not load alignment data: {error}</div></div> : null}
      {!data && !error ? <div className="va-loading">Loading standards coverage…</div> : null}

      {data && screen === 'overview' ? (
        <NationalOverview
          projects={inGrade}
          mapped={mapped}
          byState={byState}
          aggByState={aggByState}
          grade={grade}
          verification={verification}
          reviewHref={`/projects/${projectId}/review`}
          onOpenState={(s) => go({ state: s, domain: null, std: null, pid: null })}
        />
      ) : null}

      {data && screen === 'state' && state ? (
        <StateScreen
          state={state}
          projects={stateProjects}
          rows={stateRows}
          scopedRows={domainRows}
          domainName={domainName}
          grade={grade}
          filter={filter}
          onFilter={setFilter}
          onDomain={(code) => go({ domain: code, std: null, pid: null })}
          onStandard={(r) => go({ std: r.code, pid: r.projectId })}
          exportHref={`/projects/${exportProject}/exports`}
        />
      ) : null}

      {data && screen === 'standard' && stdRow && state ? (
        <StandardScreen
          row={stdRow}
          state={state}
          project={stateProjects.find((p) => p.project.id === stdRow.projectId) ?? stateProjects[0]}
          decisions={decisions[stdRow.projectId] ?? {}}
          flagged={new Set((reviewRows[stdRow.projectId] ?? []).map((r) => r.id))}
          onDecide={(itemId, d) => decide(stdRow.projectId, itemId, d)}
          storageAvailable={available}
          decideError={decideError}
        />
      ) : null}
    </div>
  )
}

// ============================ National overview ============================

function NationalOverview({
  projects,
  mapped,
  byState,
  aggByState,
  grade,
  verification,
  reviewHref,
  onOpenState,
}: {
  projects: ProjectAlign[]
  mapped: ProjectAlign[]
  byState: Record<string, ProjectAlign[]>
  aggByState: Record<string, Agg>
  grade: string
  verification: { positive: number; accepted: number; pending: number }
  reviewHref: string
  onOpenState: (s: string) => void
}) {
  const states = Object.keys(aggByState)
  const covs = states.map((s) => aggByState[s].coverage)
  const avg = covs.length ? Math.round(covs.reduce((a, b) => a + b, 0) / covs.length) : 0
  const aligned = covs.filter((c) => c >= 90).length
  const attention = covs.filter((c) => c < 75).length
  const ranked = [...states].sort((a, b) => aggByState[b].coverage - aggByState[a].coverage)
  const showAll = ranked.length <= 8
  const domains = byDomain(rowsOf(mapped))
  const curricula = [...new Set(mapped.map((p) => p.project.publisher || p.project.name).filter(Boolean))]
  const unlabeled = projects.length - mapped.length

  return (
    <section className="va-screen">
      <div className="phead">
        <span className="eyebrow accent">Alignment overview</span>
        <h1>
          Your curriculum, mapped state by state<span className="bluedot">.</span>
        </h1>
        <p className="lede">
          {mapped.length} curriculum project{mapped.length === 1 ? '' : 's'}
          {curricula.length ? ` (${curricula.join(', ')})` : ''} aligned to {states.length} state framework
          {states.length === 1 ? '' : 's'}, shown for {grade === 'all' ? 'all grades' : gradeLabel(grade).toLowerCase()}.
          Every match is traced to a page in the source, and nothing is marked verified until an expert accepts it.
          {unlabeled > 0
            ? ` ${unlabeled} project${unlabeled === 1 ? ' has' : 's have'} no state framework label yet, so ${unlabeled === 1 ? 'it is' : 'they are'} not on the map.`
            : ''}
        </p>
      </div>

      <div className="kpis">
        <Kpi label="States mapped" value={states.length} of="of 50" sub="With an aligned framework project" />
        <Kpi label="Average coverage" value={avg} unit="%" sub="Standards met, across mapped states" accent />
        <Kpi label="States fully aligned" value={aligned} of={`of ${states.length}`} sub="90%+ of standards met" />
        <Kpi label="States needing attention" value={attention} sub="Below 75% coverage" />
      </div>

      <Link className="verify-strip" to={reviewHref}>
        <span className="vs-left">
          <span className="vs-check" aria-hidden="true">
            ✓
          </span>
          <span>
            <b>{verification.accepted.toLocaleString()}</b> of {verification.positive.toLocaleString()} aligned citations
            expert-verified
          </span>
        </span>
        <span className="vs-right">
          {verification.pending > 0 ? `${verification.pending} awaiting review →` : 'Open review queue →'}
        </span>
      </Link>

      <div className="grid-2">
        <div className="panel">
          <div className="panel-head">
            <h2>Coverage by state</h2>
            <span className="meta">
              {grade === 'all' ? 'All grades' : gradeLabel(grade)} · select a state to drill in
            </span>
          </div>
          <div className="mapwrap">
            <UsMap byState={aggByState} onSelect={onOpenState} />
          </div>
          <div className="map-legend">
            <div className="legend-metric">
              <strong>Coverage</strong> is the share of a state&apos;s standards your curriculum meets in full. Partial
              matches and gaps are tracked separately. Grey states have no project yet.
            </div>
            <div className="cov-scale-wrap">
              <div className="cov-scale" aria-hidden="true">
                {COV_COLORS.map((c) => (
                  <span key={c} className="sw" style={{ background: c }} />
                ))}
              </div>
              <div className="cov-ticks">
                {COV_TICKS.map((t) => (
                  <span key={t}>{t}</span>
                ))}
              </div>
            </div>
          </div>
        </div>

        <div className="panel">
          <div className="panel-head">
            <h2>States by coverage</h2>
            <span className="meta">{showAll ? 'All mapped states' : 'Top and bottom'}</span>
          </div>
          <div className="ranklist">
            {ranked.length === 0 ? <div className="rank-empty">No state frameworks mapped for this grade yet.</div> : null}
            {showAll ? (
              ranked.map((s) => <RankItem key={s} state={s} agg={aggByState[s]} projects={byState[s]} onClick={() => onOpenState(s)} />)
            ) : (
              <>
                <div className="rank-group">Highest coverage</div>
                {ranked.slice(0, 4).map((s) => (
                  <RankItem key={s} state={s} agg={aggByState[s]} projects={byState[s]} onClick={() => onOpenState(s)} />
                ))}
                <div className="rank-group">Lowest coverage</div>
                {ranked.slice(-4).map((s) => (
                  <RankItem key={s} state={s} agg={aggByState[s]} projects={byState[s]} onClick={() => onOpenState(s)} />
                ))}
              </>
            )}
          </div>
        </div>
      </div>

      <div className="panel section-gap">
        <div className="panel-head">
          <h2>Coverage by domain</h2>
          <span className="meta">
            Across all mapped states
            <br />
            where your curriculum is strong or thin
          </span>
        </div>
        {domains.map((d) => {
          const s = shares(d)
          return <StrandBar key={d.label} name={d.label} m={s.m} p={s.p} g={s.g} />
        })}
        <div className="panel-body" style={{ paddingTop: 12 }}>
          <div className="legend-foot" style={{ marginTop: 0, paddingTop: 0, borderTop: 'none' }}>
            <div className="lf-group">
              <span className="lf-lbl">Per standard</span>
              <span className="lf-item"><span className="d" style={{ background: 'var(--met-fill)' }} />Met</span>
              <span className="lf-item"><span className="d" style={{ background: 'var(--partial-fill)' }} />Partial</span>
              <span className="lf-item"><span className="d" style={{ background: 'var(--gap)' }} />Gap</span>
            </div>
          </div>
        </div>
      </div>
    </section>
  )
}

function RankItem({ state, agg, projects, onClick }: { state: string; agg: Agg; projects: ProjectAlign[]; onClick: () => void }) {
  return (
    <button type="button" className="rank-item" onClick={onClick}>
      <div>
        <div className="rank-name">{STATE_NAMES[state]}</div>
        <div className="rank-fw">
          {frameworksOf(projects)} · {projects.map((p) => gradeLabel(p.grade)).join(', ')}
        </div>
      </div>
      <div className="rank-pct">
        {agg.coverage}
        <span className="rank-pct-u">% aligned</span>
      </div>
      <div className="rank-bar">
        <span style={{ width: `${agg.coverage}%` }} />
      </div>
    </button>
  )
}

// ============================ State / domain ============================

function StateScreen({
  state,
  projects,
  rows,
  scopedRows,
  domainName,
  grade,
  filter,
  onFilter,
  onDomain,
  onStandard,
  exportHref,
}: {
  state: string
  projects: ProjectAlign[]
  rows: Row[]
  scopedRows: Row[]
  domainName: string | null
  grade: string
  filter: Filter
  onFilter: (f: Filter) => void
  onDomain: (code: string) => void
  onStandard: (r: Row) => void
  exportHref: string
}) {
  const a = aggregate(scopedRows)
  const total = a.total || 1
  const gradeText = grade === 'all' ? projects.map((p) => gradeLabel(p.grade)).join(', ') : gradeLabel(grade)
  const multiGrade = new Set(projects.map((p) => p.grade)).size > 1
  const domains = byDomain(rows)
  const tableRows = scopedRows.filter((r) => filter === 'all' || r.status === filter)

  return (
    <section className="va-screen">
      <div className="state-hero">
        <div>
          <span className="eyebrow accent">State alignment</span>
          <h1>{domainName ?? STATE_NAMES[state]}</h1>
          <p className="sh-fw">
            {domainName ? `${STATE_NAMES[state]} · ` : ''}
            {frameworksOf(projects)} · {gradeText}
          </p>
          <div className="sh-meter" aria-hidden="true">
            <span className="seg-met" style={{ width: `${(100 * a.met) / total}%` }} />
            <span className="seg-partial" style={{ width: `${(100 * a.partial) / total}%` }} />
            <span className="seg-gap" style={{ width: `${(100 * a.gap) / total}%` }} />
          </div>
          <div className="sh-legend">
            <span className="li"><span className="d" style={{ background: 'var(--met-fill)' }} />Met <b>{a.met}</b></span>
            <span className="li"><span className="d" style={{ background: 'var(--partial-fill)' }} />Partial <b>{a.partial}</b></span>
            <span className="li"><span className="d" style={{ background: 'var(--gap)' }} />Gap <b>{a.gap}</b></span>
          </div>
        </div>
        <div>
          <div className="sh-cap">Overall coverage</div>
          <div className="sh-big">
            <span className="n">{a.coverage}</span>
            <span className="u">%</span>
          </div>
          <p className="sh-def">
            Share of {domainName ? 'this domain’s' : 'this state’s'} standards your curriculum meets in full.
          </p>
          <div style={{ marginTop: 14 }}>
            <Link className="btn" to={exportHref}>
              Download state report
            </Link>
          </div>
        </div>
      </div>

      <div className="kpis">
        <Kpi label="Standards in framework" value={a.total} sub={domainName ? 'In this domain' : gradeText} />
        <Kpi label="Met" value={a.met} sub="Full coverage" accent />
        <Kpi label="Partial" value={a.partial} sub="Needs supplementing" />
        <Kpi label="Gaps" value={a.gap} sub="No aligned resource" />
      </div>

      <div className="panel">
        <div className="panel-head">
          <h2>Coverage by domain</h2>
          <span className="meta">This state · select a domain to see its standards</span>
        </div>
        {domains.map((d) => {
          const s = shares(d)
          return (
            <StrandBar
              key={d.label}
              name={d.label}
              m={s.m}
              p={s.p}
              g={s.g}
              current={d.label === domainName}
              onClick={() => onDomain(d.code)}
            />
          )
        })}
      </div>

      <div className="panel section-gap">
        <div className="panel-head">
          <h2>{domainName ? `Standards in ${domainName}` : 'All standards'}</h2>
          <div className="filters" role="group" aria-label="Filter standards">
            {(['all', 'met', 'partial', 'gap'] as Filter[]).map((f) => (
              <button
                key={f}
                type="button"
                className={`chip${filter === f ? ' on' : ''}`}
                aria-pressed={filter === f}
                onClick={() => onFilter(f)}
              >
                {f === 'all' ? 'All' : f === 'met' ? 'Met' : f === 'partial' ? 'Partial' : 'Gaps'}
                <span className="chip-n">{f === 'all' ? a.total : a[f]}</span>
              </button>
            ))}
          </div>
        </div>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th style={{ width: '46%' }}>Standard</th>
                <th style={{ width: '14%' }}>Status</th>
                <th style={{ width: '16%' }}>Resources</th>
                <th style={{ width: '14%' }}>Coverage</th>
                <th style={{ width: '10%' }} aria-label="Open" />
              </tr>
            </thead>
            <tbody>
              {tableRows.map((r) => {
                const lessonsN = r.lessons.length
                const width = r.status === 'met' ? 100 : r.status === 'partial' ? 55 : 0
                const open = r.status !== 'gap'
                return (
                  <tr
                    key={`${r.projectId}:${r.code}`}
                    className={open ? 'rowlink' : undefined}
                    onClick={open ? () => onStandard(r) : undefined}
                    tabIndex={open ? 0 : undefined}
                    onKeyDown={open ? (e) => e.key === 'Enter' && onStandard(r) : undefined}
                  >
                    <td>
                      <div className="std-code">{r.code}</div>
                      <div className="std-strand">
                        {r.domainLabel}
                        {r.groupLabel ? ` · ${r.groupLabel}` : ''}
                        {multiGrade ? ` · ${gradeLabel(r.grade)}` : ''}
                      </div>
                      <div className="std-text">{r.text}</div>
                    </td>
                    <td>
                      <RollBadge status={r.status} fill />
                    </td>
                    <td className="cell-num">
                      {lessonsN === 0 ? (
                        <span style={{ color: 'var(--muted)' }}>None</span>
                      ) : (
                        `${lessonsN} lesson${lessonsN > 1 ? 's' : ''}`
                      )}
                    </td>
                    <td>
                      <div className={`minibar${r.status === 'partial' ? ' partial' : ''}`}>
                        <span style={{ width: `${width}%` }} />
                      </div>
                    </td>
<td style={{ textAlign: 'right' }}>{open ? <span className="drill">Evidence →</span> : null}</td>
                  </tr>
                )
              })}
              {tableRows.length === 0 ? (
                <tr>
                  <td colSpan={5} className="empty-row">
                    No standards in this status.
                  </td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>
      </div>
      <p className="screen-note">
        Status rolls up each standard: Met when at least one lesson fully aligns, Partial when only partial matches
        exist, Gap when no lesson aligns.
      </p>
    </section>
  )
}

// ============================ Standard / evidence ============================

function StandardScreen({
  row,
  state,
  project,
  decisions,
  flagged,
  onDecide,
  storageAvailable,
  decideError,
}: {
  row: Row
  state: string
  project: ProjectAlign
  decisions: Record<string, import('../components/align/data').Decision>
  flagged: Set<string>
  onDecide: (itemId: string, d: 'accepted' | 'rejected' | 'pending') => Promise<void>
  storageAvailable: boolean
  decideError: string | null
}) {
  const all = useProjectAlignments(row.projectId)
  const [busy, setBusy] = useState<string | null>(null)
  const evidence: AlignmentRow[] = useMemo(
    () => (all ?? []).filter((a) => a.standard_code === row.code && a.matched_status !== 'none'),
    [all, row.code],
  )
  const full = evidence.filter((e) => e.matched_status === 'full').length
  const partial = evidence.length - full
  const decided = evidence.map((e) => decisions[e.id]?.decision)
  const verifyLabel = !evidence.length
    ? null
    : decided.every((d) => d === 'accepted')
      ? { cls: 'met', text: 'Expert-verified' }
      : decided.some((d) => d === 'accepted')
        ? { cls: 'partial', text: `${decided.filter((d) => d === 'accepted').length} of ${evidence.length} citations verified` }
        : evidence.some((e) => flagged.has(e.id))
          ? { cls: 'partial', text: 'Pending expert review' }
          : { cls: 'gap', text: 'Not yet expert-reviewed' }

  const handle = async (id: string, d: 'accepted' | 'rejected' | 'pending') => {
    setBusy(id)
    try {
      await onDecide(id, d)
    } finally {
      setBusy(null)
    }
  }

  return (
    <section className="va-screen">
      <div className="std-banner">
        <span className="sb-code">{row.code}</span>
        <p className="sb-text">{row.text}</p>
        <div className="sb-row">
          <RollBadge status={row.status} />
          {verifyLabel ? (
            <span className={`badge fill ${verifyLabel.cls}`}>
              <span className="dot" />
              {verifyLabel.text}
            </span>
          ) : null}
          <span className="sb-meta">
            {all === null
              ? 'Loading evidence…'
              : evidence.length
                ? `across ${evidence.length} lesson${evidence.length > 1 ? 's' : ''} · ${full} full, ${partial} partial`
                : 'no aligned resources yet'}
          </span>
          <span className="sampletag">
            {STATE_NAMES[state]} · {project.framework} · {gradeLabel(project.grade)}
          </span>
        </div>
      </div>

      {!storageAvailable ? (
        <div className="va-error">Review storage is unavailable, so decisions can’t be saved right now.</div>
      ) : null}
      {decideError ? <div className="va-error">{decideError}</div> : null}

      <div className="panel">
        <div className="panel-head">
          <h2>Evidence-level alignment</h2>
          <span className="meta">Every lesson that aligns, with the evidence from your content</span>
        </div>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th style={{ width: '24%' }}>Aligned resource</th>
                <th style={{ width: '11%' }}>Match</th>
                <th style={{ width: '45%' }}>Evidence from content</th>
                <th style={{ width: '20%' }}>Verification</th>
              </tr>
            </thead>
            <tbody>
              {evidence.map((e) => (
                <tr key={e.id}>
                  <td>
                    <div className="ev-resource">
                      <strong>{lessonName(e.resource_id, e.lesson_title)}</strong>
                      <span>{e.evidence_page ? pageRange([e.evidence_page]) : 'Teacher guide'}</span>
                    </div>
                  </td>
                  <td>
                    <MatchBadge match={e.matched_status} />
                  </td>
                  <td>
                    <div className="ev-text">
                      {e.evidence ? <div className="ev-quote">“{cleanQuote(e.evidence)}”</div> : null}
                      {e.rationale}
                    </div>
                  </td>
                  <td>
                    <VerificationCell
                      decision={decisions[e.id]}
                      flagged={flagged.has(e.id)}
                      busy={busy === e.id || !storageAvailable}
                      onDecide={(d) => void handle(e.id, d)}
                    />
                  </td>
                </tr>
              ))}
              {all !== null && evidence.length === 0 ? (
                <tr>
                  <td colSpan={4} className="empty-row">
                    No lesson aligns to this standard yet.
                  </td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>
        <div className="panel-body" style={{ paddingTop: 0 }}>
          <div className="callout">
            <div className="c-lbl">Why this matters</div>
            <div className="c-txt">
              {row.status === 'partial'
                ? 'Coverage exists but has noted limits. Pairing a second lesson that addresses the full demand of the standard would move this from partial to met.'
                : 'At least one lesson teaches this standard directly, so the alignment is defensible and traces back to a page in your content.'}
            </div>
          </div>
          <div className="legend-foot">
            <div className="lf-group">
              <span className="lf-lbl">Standard roll-up</span>
              <span className="lf-item"><span className="d" style={{ background: 'var(--met-fill)' }} />Met. At least one full match exists</span>
              <span className="lf-item"><span className="d" style={{ background: 'var(--partial-fill)' }} />Partial. Only partial matches</span>
              <span className="lf-item"><span className="d" style={{ background: 'var(--gap)' }} />Gap. No aligned lessons</span>
            </div>
            <div className="lf-group">
              <span className="lf-lbl">Per lesson</span>
              <span className="lf-item"><span className="d" style={{ background: 'var(--met-fill)' }} />Full. Every clause met</span>
              <span className="lf-item"><span className="d" style={{ background: 'var(--partial-fill)' }} />Partial. Some clauses met</span>
            </div>
          </div>
        </div>
      </div>
    </section>
  )
}

export default CoverageExplorerPage
