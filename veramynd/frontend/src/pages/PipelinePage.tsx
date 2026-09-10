import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { api, withProject } from '../api/client'
import type { OverviewMetrics, PipelineStage } from '../api/types'
import { IngestRunControls } from '../components/IngestRunControls'
import { LivePipelineProgress, type PipelineJob } from '../components/LivePipelineProgress'
import { OverviewLoading } from '../components/OverviewStates'
import type { RunnableStep } from '../components/PipelineRunPanel'
import { NONE_PROJECT_ID, useProject } from '../project/ProjectContext'

function isDone(status: string) {
  return /complete|ok|healthy/i.test(status || '')
}
function isWarn(status: string) {
  return /warn/i.test(status || '')
}

function jobMatchesProject(j: PipelineJob, projectId: string) {
  if (j.project_id === projectId) return true
  if (projectId.startsWith('upload-') && j.batch_id) {
    return projectId === `upload-${j.batch_id}`
  }
  return false
}

export function PipelinePage({
  reloadKey = 0,
  projectId,
}: {
  reloadKey?: number
  projectId: string
}) {
  const { project, hasProject, loading: projectsLoading } = useProject()
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [stages, setStages] = useState<PipelineStage[]>([])
  const [overview, setOverview] = useState<OverviewMetrics | null>(null)
  const [runnableSteps, setRunnableSteps] = useState<RunnableStep[]>([])
  const [liveJob, setLiveJob] = useState<PipelineJob | null>(null)

  const logsPath = hasProject
    ? `/projects/${projectId}/logging`
    : `/projects/${NONE_PROJECT_ID}/logging`

  const load = useCallback(async () => {
    if (!hasProject) {
      setStages([])
      setOverview(null)
      setLoading(false)
      try {
        const d = await api<{
          runnable_steps?: RunnableStep[]
          active_job?: PipelineJob | null
          jobs?: PipelineJob[]
        }>('/api/pipeline/jobs?limit=5')
        setRunnableSteps(d.runnable_steps || [])
        const active =
          d.active_job ||
          d.jobs?.find((j) => j.status === 'running' || j.status === 'queued') ||
          null
        setLiveJob(active)
      } catch {
        /* ignore */
      }
      return
    }
    setLoading(true)
    setError(null)
    try {
      const [pipe, ov, jobs] = await Promise.all([
        api<{ stages: PipelineStage[]; runnable_steps?: RunnableStep[] }>(
          withProject('/api/pipeline', projectId),
        ),
        api<OverviewMetrics>(withProject('/api/overview', projectId)).catch(() => null),
        api<{ active_job?: PipelineJob | null; jobs?: PipelineJob[] }>(
          '/api/pipeline/jobs?limit=10',
        ).catch(() => ({ active_job: null, jobs: [] })),
      ])
      setStages(pipe.stages || [])
      setRunnableSteps(pipe.runnable_steps || [])
      setOverview(ov)
      const match =
        jobs.active_job && jobMatchesProject(jobs.active_job, projectId)
          ? jobs.active_job
          : jobs.jobs?.find(
              (j) =>
                (j.status === 'running' || j.status === 'queued') &&
                jobMatchesProject(j, projectId),
            ) ||
            jobs.jobs?.find((j) => jobMatchesProject(j, projectId)) ||
            null
      setLiveJob(match)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
      setStages([])
      setOverview(null)
    } finally {
      setLoading(false)
    }
  }, [hasProject, projectId])

  useEffect(() => {
    void load()
  }, [load, reloadKey])

  useEffect(() => {
    const live = liveJob?.status === 'running' || liveJob?.status === 'queued'
    if (!live || !liveJob?.id) return
    const t = window.setInterval(() => {
      void api<{ job: PipelineJob }>(`/api/pipeline/jobs/${liveJob.id}?log=false`)
        .then((d) => setLiveJob(d.job))
        .catch(() => undefined)
    }, 1500)
    return () => window.clearInterval(t)
  }, [liveJob?.id, liveJob?.status])

  const { done, pending, pct } = useMemo(() => {
    const d = stages.filter((s) => isDone(s.status)).length
    const w = stages.filter((s) => isWarn(s.status)).length
    const p = Math.max(0, stages.length - d - w)
    return {
      done: d,
      warn: w,
      pending: p,
      pct: stages.length ? Math.round((100 * d) / stages.length) : 0,
    }
  }, [stages])

  if (projectsLoading || loading) return <OverviewLoading />

  if (!hasProject) {
    return (
      <div className="analytics">
        <div className="page-header">
          <div>
            <h1>Pipeline</h1>
            <p>Live run progress — start from Ingestion or select a project.</p>
          </div>
          <div className="header-actions">
            <Link className="btn" to={logsPath}>
              Logging
            </Link>
            <Link className="btn" to={`/projects/${NONE_PROJECT_ID}/ingestion`}>
              Ingestion
            </Link>
          </div>
        </div>

        <LivePipelineProgress job={liveJob} title="Live run" />

        <section className="card">
          <div className="card-b">
            <p className="card-sub" style={{ margin: 0 }}>
              <Link to={`/projects/${NONE_PROJECT_ID}/ingestion`}>Upload inputs</Link> to run a
              batch, or pick a project to run against its output.{' '}
              <Link to={logsPath}>Open Logging</Link> for typed errors.
            </p>
          </div>
        </section>
      </div>
    )
  }

  if (error && !stages.length) {
    return (
      <div className="error-box">
        <h3>Unable to load Pipeline</h3>
        <p>{error}</p>
        <button type="button" className="btn" onClick={() => void load()}>
          Retry
        </button>
      </div>
    )
  }

  return (
    <div className="analytics">
      <div className="page-header">
        <div>
          <h1>Pipeline</h1>
          <p>
            Live run % and stage status
            {project?.name ? ` · ${project.name}` : ''}.
          </p>
        </div>
        <div className="header-actions">
          <Link className="btn" to={logsPath}>
            Logging
          </Link>
          <Link className="btn" to={`/projects/${projectId}/ingestion`}>
            Ingestion
          </Link>
        </div>
      </div>

      <LivePipelineProgress job={liveJob} title="Live run" />

      <div className="kpi-grid kpi-4">
        <div className="kpi">
          <div className="label">Artifact stages</div>
          <div className="value">
            {done}
            <span className="kpi-of">/{stages.length}</span>
          </div>
        </div>
        <div className="kpi">
          <div className="label">Live job</div>
          <div className="value" style={{ fontSize: 18 }}>
            {typeof liveJob?.percent === 'number' ? `${liveJob.percent}%` : '—'}
          </div>
        </div>
        <div className="kpi">
          <div className="label">Pending</div>
          <div className="value">{pending}</div>
        </div>
        <div className="kpi">
          <div className="label">Health</div>
          <div className="value" style={{ fontSize: 18 }}>
            {overview?.pipeline_health || '—'}
          </div>
        </div>
      </div>

      <section className="card">
        <div className="card-h">
          <h2>Artifact flow</h2>
          <span className="badge info">{pct}% complete</span>
        </div>
        <div className="card-b">
          <div className="pipe-progress">
            <div className="pipe-progress-fill" style={{ width: `${pct}%` }} />
          </div>
          <div className="flow-diagram">
            {stages.map((s, i) => (
              <div key={s.id} className="flow-item">
                {i > 0 ? <div className="flow-join" aria-hidden /> : null}
                <div className={`flow-node ${s.status}`}>
                  <div className="flow-step">{i + 1}</div>
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
            <h2>Run pipeline</h2>
            <p className="card-sub" style={{ margin: 0 }}>
              Confirm before every start. Same controls as Ingestion.
            </p>
          </div>
          <div className="log-actions">
            <Link className="btn" to={logsPath}>
              Logging
            </Link>
          </div>
        </div>
        <div className="card-b">
          <IngestRunControls
            projectId={projectId}
            projectName={project?.name || projectId}
            framework={project?.framework || ''}
            steps={runnableSteps}
            logsPath={logsPath}
            onJobChange={setLiveJob}
          />
        </div>
      </section>

      <section className="card">
        <div className="card-h">
          <h2>Stage detail</h2>
        </div>
        <div className="card-b pipe-rail">
          {stages.map((s, i) => (
            <div className="pipe-rail-row" key={s.id}>
              <div className="pipe-rail-axis">
                <span className={`pipe-rail-dot ${s.status}`} />
                {i < stages.length - 1 ? <span className="pipe-rail-line" /> : null}
              </div>
              <div className="pipe-rail-body">
                <div className="pipe-rail-top">
                  <strong>{s.name}</strong>
                  <span className={`badge ${isDone(s.status) ? 'ok' : isWarn(s.status) ? 'warn' : 'neutral'}`}>
                    {s.status}
                  </span>
                </div>
                <div className="pipe-rail-detail">{s.detail}</div>
                <div className="pipe-rail-count">{s.count}</div>
              </div>
            </div>
          ))}
        </div>
      </section>
    </div>
  )
}
