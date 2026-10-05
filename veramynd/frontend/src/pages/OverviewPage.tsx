import { useCallback, useEffect, useState } from 'react'
import { api, withProject } from '../api/client'
import type { LessonCoverageRow, OverviewMetrics, PipelineStage, ReviewItem } from '../api/types'
import type { PipelineJob } from '../components/LivePipelineProgress'
import { OverviewEmpty, OverviewLoading, OverviewRunning } from '../components/OverviewStates'
import OverviewDashboard from '../components/overview/OverviewDashboard'
import { lastReviewedLabel } from '../lib/format'
import { useProject } from '../project/ProjectContext'

/** Same rule as the Pipeline page: a job belongs to a project by id, or by upload batch. */
function jobMatchesProject(j: PipelineJob, projectId: string) {
  if (j.project_id === projectId) return true
  return projectId.startsWith('upload-') && Boolean(j.batch_id) && projectId === `upload-${j.batch_id}`
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
  const [reviewRows, setReviewRows] = useState<ReviewItem[]>([])
  const [jobs, setJobs] = useState<PipelineJob[]>([])

  const load = useCallback(async (opts?: { quiet?: boolean }) => {
    if (!opts?.quiet) {
      setLoading(true)
      setError(null)
    }
    try {
      const [ov, cov, pipe, rev, jobList] = await Promise.all([
        api<OverviewMetrics>(withProject('/api/overview', projectId)),
        api<{ rows: LessonCoverageRow[] }>(withProject('/api/lessons/coverage', projectId)),
        api<{ stages: PipelineStage[] }>(withProject('/api/pipeline', projectId)),
        // Activity panels are optional: never let them block the Overview.
        api<{ rows: ReviewItem[] }>(withProject('/api/review', projectId)).catch(() => ({ rows: [] })),
        api<{ jobs?: PipelineJob[] }>('/api/pipeline/jobs?limit=100').catch(() => ({ jobs: [] })),
      ])
      setOverview(ov)
      setCoverage(cov.rows)
      setStages(pipe.stages)
      setReviewRows(rev.rows)
      setJobs((jobList.jobs ?? []).filter((j) => jobMatchesProject(j, projectId)))
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

  return (
    <OverviewDashboard
      projectId={projectId}
      overview={overview}
      coverage={coverage}
      reviewRows={reviewRows}
      jobs={jobs}
    />
  )
}
