import { isJobActive } from '../lib/jobs'
import { JobPauseButton } from './JobPauseButton'

export type StageProgress = {
  id: string
  name: string
  detail: string
  status: string
  percent: number
}

export type PipelineJob = {
  id: string
  mode: string
  steps: string[]
  status: string
  created_at: string
  updated_at: string
  batch_id?: string | null
  project_id?: string | null
  framework?: string
  output_dir?: string
  current_step?: string | null
  completed_steps?: string[]
  exit_code?: number | null
  error?: string | null
  message?: string
  percent?: number
  stage_progress?: StageProgress[]
  steps_total?: number
  steps_done?: number
  step_pct?: number
  stage_costs?: Record<string, number>
  total_cost_usd?: number
}

type Props = {
  job: PipelineJob | null
  title?: string
  /** Receives the job after Pause / Resume so the page can update right away. */
  onJobChange?: (job: PipelineJob) => void
}

function statusBadge(status: string) {
  if (status === 'succeeded' || status === 'complete') return 'ok'
  if (status === 'failed') return 'warn'
  if (status === 'running' || status === 'queued') return 'info'
  if (status === 'paused') return 'paused'
  return 'neutral'
}

export function LivePipelineProgress({ job, title = 'Live run', onJobChange }: Props) {
  if (!job) {
    return (
      <section className="card live-pipe-card">
        <div className="card-h">
          <h2>{title}</h2>
          <span className="badge neutral">idle</span>
        </div>
        <div className="card-b">
          <p className="card-sub" style={{ margin: 0 }}>
            No active pipeline job. Start a full or step run below — progress and % update here live.
          </p>
        </div>
      </section>
    )
  }

  const pct = typeof job.percent === 'number' ? job.percent : 0
  const stages = job.stage_progress || []
  const live = isJobActive(job.status)

  return (
    <section className={`card live-pipe-card ${live ? 'is-live' : ''}`}>
      <div className="card-h">
        <h2>{title}</h2>
        <div className="live-pipe-actions">
          <JobPauseButton job={job} onChange={onJobChange} />
          <span className={`badge ${statusBadge(job.status)}`}>
            {job.status} · {pct}%
          </span>
        </div>
      </div>
      <div className="card-b">
        <div className="live-pipe-meta">
          <code>{job.id}</code>
          <span>
            {job.steps_done ?? 0}/
            {job.steps_total ?? (stages.length || job.steps?.length || 0)} stages
          </span>
          {job.current_step ? <span>current: {job.current_step}</span> : null}
        </div>

        <div className="live-pipe-pct" aria-label={`Pipeline ${pct} percent`}>
          <div className="live-pipe-pct-track">
            <div
              className={`live-pipe-pct-fill ${job.status}`}
              style={{ width: `${pct}%` }}
            />
          </div>
          <div className="live-pipe-pct-label">{pct}%</div>
        </div>

        <div className="live-stage-grid">
          {stages.map((s, i) => (
            <div key={s.id} className={`live-stage ${s.status}`}>
              <div className="live-stage-top">
                <span className="live-stage-num">{i + 1}</span>
                <strong>{s.name}</strong>
                <span className="live-stage-pct">{s.percent}%</span>
              </div>
              <div className="live-stage-bar">
                <div className="live-stage-bar-fill" style={{ width: `${s.percent}%` }} />
              </div>
              <div className="live-stage-detail">{s.detail}</div>
            </div>
          ))}
        </div>

        {job.status === 'failed' || job.status === 'cancelled' ? (
          <div className="run-error" role="alert">
            <strong>{job.status === 'failed' ? 'Run failed' : 'Run stopped'}</strong>
            <span>{job.error || job.message || 'The run stopped without a message. Open Logging for details.'}</span>
            {job.error && job.message && job.message !== job.error ? <span>{job.message}</span> : null}
          </div>
        ) : job.message ? (
          <p className="live-pipe-msg">{job.message}</p>
        ) : null}
      </div>
    </section>
  )
}
