import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { api, withProject } from '../api/client'
import type { LessonCoverageRow, OverviewMetrics, PipelineStage } from '../api/types'
import { OverviewEmpty, OverviewLoading, OverviewRunning } from '../components/OverviewStates'
import { lastReviewedLabel, lessonMeta } from '../lib/format'
import { useProject } from '../project/ProjectContext'

type UnitStat = {
  unit: number
  rows: Array<LessonCoverageRow & { meta: ReturnType<typeof lessonMeta> }>
  aligned: number
  avg: number
  count: number
}

const CHART = {
  green: '#006437',
  greenSoft: '#34d399',
  greenMid: '#059669',
  amber: '#d97706',
  teal: '#0f766e',
  slate: '#94a3b8',
  grid: '#e8ecea',
  ink: '#111827',
  muted: '#6b7280',
}

const tooltipStyle = {
  background: '#fff',
  border: '1px solid rgba(17,24,39,0.08)',
  borderRadius: 12,
  boxShadow: '0 8px 24px rgba(17,24,39,0.08)',
  fontSize: 12,
}

function fileName(path: string) {
  const parts = path.replace(/\\/g, '/').split('/')
  return parts[parts.length - 1] || path
}

function deriveReadiness(
  overview: OverviewMetrics | null,
  stages: PipelineStage[],
): 'empty' | 'running' | 'ready' {
  if (overview?.readiness) return overview.readiness
  if (overview && overview.alignments > 0) return 'ready'
  if (overview && (overview.lessons > 0 || overview.standards > 0)) return 'running'
  if (stages.some((s) => s.status === 'complete' || s.status === 'warning')) return 'running'
  return 'empty'
}

export function OverviewPage({
  reloadKey = 0,
  projectId,
}: {
  reloadKey?: number
  projectId: string
}) {
  const { project, projects, loading: projectsLoading } = useProject()
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [overview, setOverview] = useState<OverviewMetrics | null>(null)
  const [coverage, setCoverage] = useState<LessonCoverageRow[]>([])
  const [stages, setStages] = useState<PipelineStage[]>([])

  const load = useCallback(async (opts?: { quiet?: boolean }) => {
    if (!opts?.quiet) {
      setLoading(true)
      setError(null)
    }
    try {
      const [ov, cov, pipe] = await Promise.all([
        api<OverviewMetrics>(withProject('/api/overview', projectId)),
        api<{ rows: LessonCoverageRow[] }>(withProject('/api/lessons/coverage', projectId)),
        api<{ stages: PipelineStage[] }>(withProject('/api/pipeline', projectId)),
      ])
      setOverview(ov)
      setCoverage(cov.rows)
      setStages(pipe.stages)
      setError(null)
    } catch (e) {
      if (!opts?.quiet) {
        setError(e instanceof Error ? e.message : String(e))
        setOverview(null)
        setCoverage([])
        setStages([])
      }
    } finally {
      if (!opts?.quiet) setLoading(false)
    }
  }, [projectId])

  useEffect(() => {
    void load()
  }, [load, reloadKey])

  useEffect(() => {
    const r = overview?.readiness
    if (r !== 'empty' && r !== 'running') return
    const t = window.setInterval(() => {
      void load({ quiet: true })
    }, 2500)
    return () => window.clearInterval(t)
  }, [overview?.readiness, load])

  const unitStats: UnitStat[] = useMemo(() => {
    const lessonRows = [...coverage]
      .map((row) => ({ ...row, meta: lessonMeta(row.resource_id) }))
      .sort((a, b) => a.meta.unit - b.meta.unit || a.meta.lesson - b.meta.lesson)
    const units = [...new Set(lessonRows.map((x) => x.meta.unit).filter(Boolean))]
    return units.map((u) => {
      const rows = lessonRows.filter((x) => x.meta.unit === u)
      const aligned = rows.reduce((s, x) => s + (x.aligned || 0), 0)
      const avg = Math.round(aligned / Math.max(1, rows.length))
      return { unit: u, rows, aligned, avg, count: rows.length }
    })
  }, [coverage])

  if (projectsLoading || loading) {
    return <OverviewLoading />
  }

  if (!projects.length) {
    return <OverviewEmpty onReload={() => void load()} />
  }

  if (error && !overview) {
    return (
      <div className="error-box">
        <h3>Unable to load Overview</h3>
        <p>{error}</p>
        <p style={{ fontSize: 12, color: 'var(--muted)' }}>
          Make sure the backend API is running (start it from <code>veramynd/backend</code>), then refresh.
        </p>
        <button type="button" className="btn" onClick={() => void load()}>
          Retry
        </button>
      </div>
    )
  }

  const readiness = deriveReadiness(overview, stages)
  const inputs = project?.inputs

  if (readiness === 'empty') {
    return (
      <div className="analytics analytics-state">
        <section className="project-banner banner-empty">
          <div className="project-banner-main">
            <div className="project-banner-kicker">Project</div>
            <h2 className="project-banner-title">{project?.name || projectId}</h2>
            <p className="project-banner-sub">No pipeline output yet for this project.</p>
          </div>
        </section>
        <OverviewEmpty onReload={() => void load()} projectName={project?.name} />
      </div>
    )
  }

  if (readiness === 'running') {
    const reviewedRunning = lastReviewedLabel(overview?.last_reviewed)
    return (
      <div className="analytics analytics-state">
        <section className="project-banner banner-running">
          <div className="project-banner-main">
            <div className="project-banner-copy">
              <div className="project-banner-kicker">Project · in progress</div>
              <h2 className="project-banner-title">{project?.name || projectId}</h2>
              <p className="project-banner-sub">
                Pipeline artifacts are appearing. Overview unlocks when judge results land.
              </p>
            </div>
            {reviewedRunning ? (
              <p className="project-banner-reviewed">{reviewedRunning}</p>
            ) : null}
          </div>
          <div className="project-inputs">
            <div className="project-input">
              <span className="pi-label">PDF</span>
              <strong title={inputs?.guide_pdf}>{fileName(inputs?.guide_pdf || '—')}</strong>
              <em className={inputs?.guide_pdf_exists ? 'ok' : 'missing'}>
                {inputs?.guide_pdf_exists ? 'found' : 'missing'}
              </em>
            </div>
            <div className="project-input">
              <span className="pi-label">XLSX</span>
              <strong title={inputs?.standards_xlsx}>{fileName(inputs?.standards_xlsx || '—')}</strong>
              <em className={inputs?.standards_xlsx_exists ? 'ok' : 'missing'}>
                {inputs?.standards_xlsx_exists ? 'found' : 'missing'}
              </em>
            </div>
            <div className="project-input">
              <span className="pi-label">Output</span>
              <strong title={project?.output_dir}>{project?.output_dir || '—'}</strong>
              <em className="running-tag">running</em>
            </div>
          </div>
        </section>
        <OverviewRunning
          stages={stages}
          lessons={overview?.lessons || 0}
          standards={overview?.standards || 0}
          onReload={() => void load()}
          projectName={project?.name}
          live={Boolean(overview?.live_job)}
          liveStep={overview?.live_job?.current_step || null}
        />
      </div>
    )
  }

  if (!overview) {
    return <OverviewEmpty onReload={() => void load()} projectName={project?.name} />
  }

  const total = overview.alignments || 1
  const f = overview.by_status.full || 0
  const p = overview.by_status.partial || 0
  const n = overview.by_status.none || 0
  const r = overview.review_required || 0
  const fullPct = Math.round((100 * f) / total)
  const maxAligned = Math.max(1, ...unitStats.flatMap((u) => u.rows.map((x) => x.aligned || 0)))
  const reviewed = lastReviewedLabel(overview.last_reviewed)
  const lastUpdate = reviewed ? reviewed.replace(/^Last reviewed\s+/i, 'Updated ') : 'Updated recently'
  const peakUnit = unitStats.reduce<(typeof unitStats)[number] | null>(
    (best, u) => (!best || u.avg > best.avg ? u : best),
    null,
  )

  const unitChart = unitStats.map((u) => ({
    name: `U${u.unit}`,
    avg: u.avg,
    aligned: u.aligned,
    lessons: u.count,
  }))

  const mixChart = [
    { name: 'Full', value: f, color: CHART.green },
    { name: 'Partial', value: p, color: CHART.amber },
    { name: 'Review', value: r, color: CHART.teal },
    { name: 'None', value: n, color: CHART.slate },
  ]

  const activityChart = [...coverage]
    .map((row) => ({ ...row, meta: lessonMeta(row.resource_id) }))
    .sort((a, b) => a.meta.unit - b.meta.unit || a.meta.lesson - b.meta.lesson)
    .slice(0, 12)
    .map((row) => ({
      name: row.meta.short.replace(/^U(\d+)L(\d+)/i, 'U$1·L$2'),
      full: row.full || 0,
      partial: row.partial || 0,
      none: row.none || 0,
      aligned: row.aligned || 0,
    }))

  const mapChart = [...coverage]
    .map((row) => ({ ...row, meta: lessonMeta(row.resource_id) }))
    .sort((a, b) => a.meta.unit - b.meta.unit || a.meta.lesson - b.meta.lesson)
    .map((row) => ({
      name: row.meta.short.replace(/^U(\d+)L(\d+)/i, 'L$2'),
      unit: `U${row.meta.unit}`,
      aligned: row.aligned || 0,
      full: row.full || 0,
      partial: row.partial || 0,
    }))

  const topLessons = [...coverage]
    .map((row) => ({ ...row, meta: lessonMeta(row.resource_id) }))
    .sort((a, b) => (b.aligned || 0) - (a.aligned || 0))
    .slice(0, 5)

  return (
    <div className="analytics ov-dash edtech-dash">
      <div className="ov-head">
        <div>
          <h2 className="ov-title">Overview</h2>
          <p className="ov-sub">
            Alignment summary for <strong>{project?.name || projectId}</strong>.
          </p>
        </div>
        <div className="ov-head-actions">
          <span className={`ov-status-pill ${overview.pipeline_health === 'Healthy' ? 'ok' : 'warn'}`}>
            {overview.pipeline_health}
          </span>
          <span className="ov-updated">{lastUpdate}</span>
        </div>
      </div>

      <div className="ov-kpi-grid ov-kpi-4">
        {[
          {
            label: 'Alignments',
            value: overview.alignments.toLocaleString(),
            delta: `${fullPct}% full`,
            tone: 'a',
            hint: 'Judge evaluations',
          },
          {
            label: 'Coverage',
            value: `${overview.alignment_coverage_pct}%`,
            delta: `+${overview.positive_standards_cited}`,
            tone: 'b',
            hint: `${overview.standards_leaves} leaf standards`,
          },
          {
            label: 'Review queue',
            value: String(overview.review_required),
            delta: `${overview.escalated} esc`,
            tone: 'c',
            hint: 'Needs human check',
          },
          {
            label: 'Lessons',
            value: String(overview.lessons),
            delta: `${overview.standards} std`,
            tone: 'd',
            hint: 'In this project',
          },
        ].map((kpi) => (
          <article className={`ov-kpi ed-kpi tone-${kpi.tone}`} key={kpi.label}>
            <div className="ov-kpi-top">
              <span className="ov-kpi-label">{kpi.label}</span>
              <span className="ed-delta">{kpi.delta}</span>
            </div>
            <div className="ov-kpi-value">{kpi.value}</div>
            <div className="ov-kpi-foot">
              <em>{kpi.hint}</em>
            </div>
          </article>
        ))}
      </div>

      <div className="ed-main-grid">
        <section className="ov-card ed-chart-card">
          <div className="ov-card-h">
            <div>
              <h2>Coverage by unit</h2>
              <p>Average aligned standards per lesson</p>
            </div>
            {peakUnit ? <span className="ov-chart-chip">Peak U{peakUnit.unit}</span> : null}
          </div>
          <div className="ov-card-b chart-body">
            <ResponsiveContainer width="100%" height={260}>
              <BarChart data={unitChart} margin={{ top: 8, right: 8, left: -12, bottom: 0 }}>
                <CartesianGrid stroke={CHART.grid} strokeDasharray="3 6" vertical={false} />
                <XAxis
                  dataKey="name"
                  tick={{ fill: CHART.muted, fontSize: 12, fontWeight: 600 }}
                  axisLine={false}
                  tickLine={false}
                />
                <YAxis
                  tick={{ fill: CHART.muted, fontSize: 11 }}
                  axisLine={false}
                  tickLine={false}
                  allowDecimals={false}
                />
                <Tooltip
                  cursor={{ fill: 'rgba(0,100,55,0.05)' }}
                  contentStyle={tooltipStyle}
                  formatter={(value, name) => [value as number, name === 'avg' ? 'Avg aligned' : String(name)]}
                  labelFormatter={(label) => `Unit ${String(label).replace(/^U/, '')}`}
                />
                <Bar dataKey="avg" name="avg" radius={[8, 8, 0, 0]} maxBarSize={44}>
                  {unitChart.map((entry) => (
                    <Cell
                      key={entry.name}
                      fill={entry.name === `U${peakUnit?.unit}` ? CHART.green : CHART.greenSoft}
                    />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </section>

        <section className="ov-card ed-side-card">
          <div className="ov-card-h">
            <div>
              <h2>Alignment mix</h2>
              <p>{overview.alignments.toLocaleString()} evaluations</p>
            </div>
          </div>
          <div className="ov-card-b ov-mix-body">
            <div className="ov-mix-donut">
              <ResponsiveContainer width="100%" height="100%">
                <PieChart margin={{ top: 12, right: 12, bottom: 12, left: 12 }}>
                  <Pie
                    data={mixChart}
                    dataKey="value"
                    nameKey="name"
                    cx="50%"
                    cy="50%"
                    innerRadius="46%"
                    outerRadius="70%"
                    paddingAngle={3}
                    cornerRadius={4}
                    stroke="#fff"
                    strokeWidth={2}
                    isAnimationActive={false}
                  >
                    {mixChart.map((entry) => (
                      <Cell key={entry.name} fill={entry.color} />
                    ))}
                  </Pie>
                  <Tooltip
                    contentStyle={tooltipStyle}
                    formatter={(value) => [(value as number).toLocaleString(), 'Count']}
                  />
                </PieChart>
              </ResponsiveContainer>
              <div className="ov-mix-center" aria-hidden="true">
                <strong>{fullPct}%</strong>
                <span>Full</span>
              </div>
            </div>
            <div className="ov-mix-legend">
              {mixChart.map((row) => (
                <div className="ov-mix-legend-row" key={row.name}>
                  <span>
                    <i style={{ background: row.color }} />
                    {row.name}
                  </span>
                  <em>{row.value.toLocaleString()}</em>
                  <strong>{Math.round((100 * row.value) / total)}%</strong>
                </div>
              ))}
            </div>
          </div>
        </section>
      </div>

      <div className="ed-main-grid ed-second">
        <section className="ov-card">
          <div className="ov-card-h">
            <div>
              <h2>Recent lesson activity</h2>
              <p>Full · partial · none by lesson</p>
            </div>
          </div>
          <div className="ov-card-b chart-body">
            <ResponsiveContainer width="100%" height={280}>
              <BarChart data={activityChart} margin={{ top: 8, right: 8, left: -12, bottom: 28 }}>
                <CartesianGrid stroke={CHART.grid} strokeDasharray="3 6" vertical={false} />
                <XAxis
                  dataKey="name"
                  tick={{ fill: CHART.muted, fontSize: 10, fontWeight: 600 }}
                  axisLine={false}
                  tickLine={false}
                  interval={0}
                  angle={-28}
                  textAnchor="end"
                  height={48}
                />
                <YAxis
                  tick={{ fill: CHART.muted, fontSize: 11 }}
                  axisLine={false}
                  tickLine={false}
                  allowDecimals={false}
                />
                <Tooltip contentStyle={tooltipStyle} />
                <Legend
                  verticalAlign="top"
                  height={28}
                  iconType="circle"
                  wrapperStyle={{ fontSize: 12, color: CHART.muted }}
                />
                <Bar dataKey="full" stackId="a" fill={CHART.green} name="Full" radius={[0, 0, 0, 0]} maxBarSize={36} />
                <Bar dataKey="partial" stackId="a" fill={CHART.amber} name="Partial" maxBarSize={36} />
                <Bar dataKey="none" stackId="a" fill={CHART.slate} name="None" radius={[6, 6, 0, 0]} maxBarSize={36} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </section>

        <section className="ov-card ed-side-card">
          <div className="ov-card-h">
            <div>
              <h2>Top lessons</h2>
              <p>Highest alignment coverage</p>
            </div>
          </div>
          <div className="ov-card-b ed-rank-list">
            {topLessons.map((row, i) => {
              const w = Math.round((100 * (row.aligned || 0)) / maxAligned)
              return (
                <div className="ed-rank-row" key={row.resource_id}>
                  <span className="ed-rank-n">{i + 1}</span>
                  <div className="ed-rank-body">
                    <div className="ed-rank-top">
                      <strong>{row.meta.short}</strong>
                      <em>{row.aligned}</em>
                    </div>
                    <div className="ed-rank-bar">
                      <span style={{ width: `${w}%` }} />
                    </div>
                  </div>
                </div>
              )
            })}
          </div>
        </section>
      </div>

      <section className="ov-card">
        <div className="ov-card-h">
          <div>
            <h2>Lesson coverage map</h2>
            <p>Aligned standards across every lesson in the project</p>
          </div>
        </div>
        <div className="ov-card-b chart-body">
          <ResponsiveContainer width="100%" height={300}>
            <AreaChart data={mapChart} margin={{ top: 10, right: 12, left: -8, bottom: 28 }}>
              <defs>
                <linearGradient id="covFill" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor={CHART.green} stopOpacity={0.28} />
                  <stop offset="100%" stopColor={CHART.green} stopOpacity={0.02} />
                </linearGradient>
              </defs>
              <CartesianGrid stroke={CHART.grid} strokeDasharray="3 6" vertical={false} />
              <XAxis
                dataKey="name"
                tick={{ fill: CHART.muted, fontSize: 10, fontWeight: 600 }}
                axisLine={false}
                tickLine={false}
                interval="preserveStartEnd"
                angle={-25}
                textAnchor="end"
                height={48}
              />
              <YAxis
                tick={{ fill: CHART.muted, fontSize: 11 }}
                axisLine={false}
                tickLine={false}
                allowDecimals={false}
              />
              <Tooltip
                contentStyle={tooltipStyle}
                labelFormatter={(_, payload) => {
                  const row = payload?.[0]?.payload as { unit?: string; name?: string } | undefined
                  return row ? `${row.unit} · ${row.name}` : ''
                }}
              />
              <Area
                type="monotone"
                dataKey="aligned"
                name="Aligned"
                stroke={CHART.green}
                strokeWidth={2.5}
                fill="url(#covFill)"
                dot={{ r: 3, fill: CHART.green, strokeWidth: 0 }}
                activeDot={{ r: 5, fill: CHART.greenMid }}
              />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      </section>
    </div>
  )
}
