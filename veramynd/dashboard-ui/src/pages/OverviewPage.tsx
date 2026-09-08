import { useCallback, useEffect, useMemo, useState, type CSSProperties } from 'react'
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

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const [ov, cov, pipe] = await Promise.all([
        api<OverviewMetrics>(withProject('/api/overview', projectId)),
        api<{ rows: LessonCoverageRow[] }>(withProject('/api/lessons/coverage', projectId)),
        api<{ stages: PipelineStage[] }>(withProject('/api/pipeline', projectId)),
      ])
      setOverview(ov)
      setCoverage(cov.rows)
      setStages(pipe.stages)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
      setOverview(null)
      setCoverage([])
      setStages([])
    } finally {
      setLoading(false)
    }
  }, [projectId])

  useEffect(() => {
    void load()
  }, [load, reloadKey])

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
          Make sure FastAPI is running on http://127.0.0.1:8765
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
  const p1 = (f / total) * 100
  const p2 = p1 + (p / total) * 100
  const p3 = p2 + (r / total) * 100
  const fullPct = Math.round((100 * f) / total)
  const maxAligned = Math.max(1, ...unitStats.flatMap((u) => u.rows.map((x) => x.aligned || 0)))
  const maxUnitAvg = Math.max(1, ...unitStats.map((x) => x.avg))
  const reviewed = lastReviewedLabel(overview.last_reviewed)

  return (
    <div className="analytics">
      <section className="project-banner">
        <div className="project-banner-main">
          <div className="project-banner-copy">
            <div className="project-banner-kicker">
              Project{project?.is_default ? ' · default' : ''}
            </div>
            <h2 className="project-banner-title">{project?.name || projectId}</h2>
            <p className="project-banner-sub">
              One Overview = one PDF + one XLSX + that project&apos;s output.
            </p>
          </div>
          {reviewed ? (
            <p className="project-banner-reviewed">{reviewed}</p>
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
            <em className={project?.has_output ? 'ok' : 'missing'}>
              {project?.has_output ? 'ready' : 'empty'}
            </em>
          </div>
        </div>
      </section>

      <div className="kpi-grid kpi-4">
        <div className="kpi">
          <div className="label">Alignments</div>
          <div className="value">{overview.alignments.toLocaleString()}</div>
          <div className="hint">Judge evaluations in scope</div>
        </div>
        <div className="kpi">
          <div className="label">Coverage</div>
          <div className="value">{overview.alignment_coverage_pct}%</div>
          <div className="hint">
            {overview.positive_standards_cited} of {overview.standards_leaves} leaf standards
          </div>
        </div>
        <div className="kpi">
          <div className="label">Review</div>
          <div className="value">{overview.review_required}</div>
          <div className="hint">{overview.escalated} escalated</div>
        </div>
        <div className="kpi">
          <div className="label">Lessons</div>
          <div className="value">{overview.lessons}</div>
          <div className="hint">
            Pipeline {overview.pipeline_health.toLowerCase()}
          </div>
        </div>
      </div>

      <div className="grid-2">
        <section className="card">
          <div className="card-h">
            <div>
              <h2>Alignment mix</h2>
              <p className="card-sub">{overview.alignments.toLocaleString()} total evaluations</p>
            </div>
          </div>
          <div className="card-b">
            <div className="donut-wrap compact">
              <div className="donut-center">
                <div
                  className="donut"
                  style={
                    {
                      ['--p1' as string]: `${p1}%`,
                      ['--p2' as string]: `${p2}%`,
                      ['--p3' as string]: `${p3}%`,
                    } as CSSProperties
                  }
                />
                <div className="donut-label">
                  <strong>{fullPct}%</strong>
                  <span>Full</span>
                </div>
              </div>
              <div className="legend tight">
                {[
                  { label: 'Full', color: 'var(--ok)', count: f },
                  { label: 'Partial', color: 'var(--warn)', count: p },
                  { label: 'Review', color: 'var(--blue)', count: r },
                  { label: 'None', color: '#cbd5e1', count: n },
                ].map((row) => (
                  <div className="legend-row" key={row.label}>
                    <span>
                      <span className="swatch" style={{ background: row.color }} />
                      {row.label}
                    </span>
                    <span className="legend-vals">
                      <strong>{row.count}</strong>
                      <small>{Math.round((100 * row.count) / total)}%</small>
                    </span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </section>

        <section className="card">
          <div className="card-h">
            <div>
              <h2>Coverage by unit</h2>
              <p className="card-sub">Average aligned standards per lesson</p>
            </div>
          </div>
          <div className="card-b">
            <div className="unit-chart">
              {unitStats.map((u) => {
                const w = Math.round((100 * u.avg) / maxUnitAvg)
                return (
                  <div className="unit-bar-row" key={u.unit}>
                    <div className="unit-lab-block">
                      <span className="unit-lab">Unit {u.unit}</span>
                      <span className="unit-lessons">{u.count} lessons</span>
                    </div>
                    <div className="unit-track">
                      <div className="unit-fill" style={{ width: `${w}%` }} />
                    </div>
                    <span className="unit-val">
                      {u.avg}
                      <small>avg</small>
                    </span>
                  </div>
                )
              })}
            </div>
          </div>
        </section>
      </div>

      <section className="card">
        <div className="card-h">
          <div>
            <h2>Pipeline flow</h2>
            <p className="card-sub">Stage status for this project</p>
          </div>
          <span className={`badge ${overview.pipeline_health === 'Healthy' ? 'ok' : 'info'}`}>
            {overview.pipeline_health}
          </span>
        </div>
        <div className="card-b">
          <div className="flow-diagram flow-animated">
            {stages.map((s, i) => (
              <div key={s.id} className="flow-item" style={{ ['--i' as string]: i }}>
                {i > 0 ? <div className="flow-join" aria-hidden /> : null}
                <div className={`flow-node ${s.status}`} title={s.detail}>
                  <div className={`flow-dot ${s.status}`} aria-hidden />
                  <div className="flow-name">{s.name}</div>
                  <div className="flow-meta">{s.count}</div>
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section className="card">
        <div className="card-h">
          <div>
            <h2>Lesson coverage map</h2>
            <p className="card-sub">Aligned standards per lesson (darker = more coverage)</p>
          </div>
          <div className="heat-scale">
            <span>Low</span>
            <div className="heat-grad" />
            <span>High</span>
          </div>
        </div>
        <div className="card-b">
          <div className="heat-board">
            {unitStats.map((u) => (
              <div className="heat-unit" key={u.unit}>
                <div className="heat-unit-lab">
                  <strong>U{u.unit}</strong>
                  <span>{u.count}</span>
                </div>
                <div className="heat-grid">
                  {u.rows.map((row) => {
                    const intensity = (row.aligned || 0) / maxAligned
                    const bg = `rgba(31,111,91,${(0.1 + intensity * 0.72).toFixed(3)})`
                    return (
                      <button
                        key={row.resource_id}
                        type="button"
                        className="heat-cell"
                        style={{ background: bg }}
                        title={`${row.meta.short} · ${row.aligned} aligned · F${row.full}/P${row.partial}/N${row.none}`}
                      >
                        <span>{row.meta.short.replace(/^U\d+L/i, 'L')}</span>
                        <em>{row.aligned}</em>
                      </button>
                    )
                  })}
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>
    </div>
  )
}
