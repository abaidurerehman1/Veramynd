import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { api, withProject } from '../api/client'
import { ConfirmDialog } from './ConfirmDialog'
import { isJobActive } from '../lib/jobs'
import { JobPauseButton } from './JobPauseButton'
import type { PipelineJob } from './LivePipelineProgress'
import type { RunnableStep } from './PipelineRunPanel'
import { detailMessage, friendlyError } from '../lib/errors'

type Mode = 'auto' | 'stepwise'

type Props = {
  batchId?: string | null
  projectId?: string | null
  projectName?: string | null
  framework?: string
  steps: RunnableStep[]
  logsPath?: string
  onJobChange?: (job: PipelineJob | null) => void
}

async function postRun(body: Record<string, unknown>): Promise<{ job: PipelineJob }> {
  const res = await fetch('/api/pipeline/run', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  const data = await res.json().catch(() => ({}))
  if (!res.ok) {
    throw new Error(detailMessage(data, res.status))
  }
  return data as { job: PipelineJob }
}

function statusClass(status: string) {
  if (status === 'succeeded') return 'ok'
  if (status === 'failed') return 'warn'
  if (status === 'running' || status === 'queued') return 'info'
  if (status === 'paused') return 'paused'
  return 'neutral'
}

function resolveProjectId(batchId: string | null, projectId: string | null) {
  if (projectId) return projectId
  if (batchId) return `upload-${batchId}`
  return ''
}

export function IngestRunControls({
  batchId = null,
  projectId = null,
  projectName = null,
  framework = '',
  steps,
  logsPath,
  onJobChange,
}: Props) {
  const [mode, setMode] = useState<Mode>('auto')
  const [artifactDone, setArtifactDone] = useState<string[]>([])
  const [nextArtifactStep, setNextArtifactStep] = useState<string | null>(null)
  const [sessionDone, setSessionDone] = useState<string[]>([])
  const [job, setJob] = useState<PipelineJob | null>(null)
  const [log, setLog] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [pending, setPending] = useState<'full' | string | null>(null)

  const resolvedProjectId = resolveProjectId(batchId, projectId)
  const targetKey = batchId || projectId || ''
  const targetLabel = batchId
    ? `batch ${batchId}`
    : projectName || projectId || 'this project'
  const writeWhere = batchId
    ? `uploads/${batchId}/output/`
    : 'this project’s output folder'
  // A paused job still holds the pipeline: keep polling it and keep new runs disabled.
  const running = isJobActive(job?.status)
  const paused = job?.status === 'paused'
  const onPauseChange = (next: PipelineJob) => {
    setJob(next)
    onJobChange?.(next)
  }
  const targetOk = Boolean(batchId || projectId)

  const doneIds = useMemo(() => {
    const set = new Set([...artifactDone, ...sessionDone])
    // Keep prefix order from runnable steps so UI stays sequential
    return steps.map((s) => s.id).filter((id) => set.has(id))
  }, [artifactDone, sessionDone, steps])

  const syncArtifacts = useCallback(async () => {
    if (!resolvedProjectId) {
      setArtifactDone([])
      return
    }
    try {
      const data = await api<{ completed_steps?: string[]; next_step?: string | null }>(
        withProject('/api/pipeline', resolvedProjectId),
      )
      setArtifactDone(Array.isArray(data.completed_steps) ? data.completed_steps : [])
      setNextArtifactStep(data.next_step ?? null)
    } catch {
      /* keep last known */
    }
  }, [resolvedProjectId])

  const refreshJob = useCallback(
    async (id: string) => {
      const data = await api<{ job: PipelineJob; log?: string }>(`/api/pipeline/jobs/${id}`)
      setJob(data.job)
      onJobChange?.(data.job)
      if (typeof data.log === 'string') setLog(data.log)
      if (data.job.status === 'succeeded') {
        if (data.job.mode === 'step' && data.job.steps?.[0]) {
          setSessionDone((prev) =>
            prev.includes(data.job.steps[0]) ? prev : [...prev, data.job.steps[0]],
          )
        }
        if (data.job.mode === 'full') {
          setSessionDone(steps.map((s) => s.id))
        }
        if (data.job.completed_steps?.length) {
          setSessionDone((prev) => {
            const next = new Set(prev)
            for (const sid of data.job.completed_steps || []) next.add(sid)
            return [...next]
          })
        }
        await syncArtifacts()
      }
      return data.job
    },
    [onJobChange, steps, syncArtifacts],
  )

  useEffect(() => {
    if (!job?.id || !running) return
    const t = window.setInterval(() => {
      void refreshJob(job.id).catch(() => undefined)
    }, 1500)
    return () => window.clearInterval(t)
  }, [job?.id, running, refreshJob])

  useEffect(() => {
    setSessionDone([])
    setJob(null)
    setLog('')
    setError(null)
    setPending(null)
    void syncArtifacts()
    // Pick up a run already in progress for this target (e.g. after a reload) so it can be paused here.
    let cancelled = false
    void api<{ active_job?: PipelineJob | null }>('/api/pipeline/jobs?limit=5')
      .then((d) => {
        const a = d.active_job
        if (cancelled || !a || !isJobActive(a.status)) return
        const mine = (resolvedProjectId && a.project_id === resolvedProjectId) || (batchId && a.batch_id === batchId)
        if (mine) {
          setJob(a)
          onJobChange?.(a)
        }
      })
      .catch(() => undefined)
    return () => {
      cancelled = true
    }
    // onJobChange is a parent callback; re-running on its identity would reset the panel.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [targetKey, syncArtifacts, resolvedProjectId, batchId])

  // Keep step wizard in sync while idle (e.g. Parse finished from another tab)
  useEffect(() => {
    if (running || !resolvedProjectId) return
    const t = window.setInterval(() => {
      void syncArtifacts()
    }, 4000)
    return () => window.clearInterval(t)
  }, [running, resolvedProjectId, syncArtifacts])

  const nextStep = useMemo(() => {
    return steps.find((s) => !doneIds.includes(s.id)) || null
  }, [steps, doneIds])

  const progressPct = steps.length ? Math.round((100 * doneIds.length) / steps.length) : 0

  const dialogCopy = useMemo(() => {
    const resumeHint =
      artifactDone.length > 0
        ? `\n\nResume: already complete → ${artifactDone.join(', ')}.${
            nextArtifactStep ? ` Continues from ${nextArtifactStep}.` : ''
          } Within a step (e.g. Normalize), lesson progress resumes from disk.`
        : ''
    if (pending === 'full') {
      return {
        title: artifactDone.length ? 'Resume complete pipeline?' : 'Run complete pipeline?',
        body: `Run parse → normalize → embed → retrieve → judge → report for ${targetLabel}. Finished stages are skipped from saved output. This calls live APIs, may take a long time, and writes to ${writeWhere}.${resumeHint}`,
        confirmLabel: artifactDone.length ? 'Resume complete auto' : 'Run complete auto',
      }
    }
    if (typeof pending === 'string') {
      const s = steps.find((x) => x.id === pending)
      return {
        title: `Confirm step: ${s?.name || pending}`,
        body: `${s?.detail || ''}\n\nTarget: ${targetLabel}. Prior completed stages stay on disk; this step resumes if partially done. Writes to ${writeWhere}.${resumeHint}`,
        confirmLabel: 'Confirm & run this step',
      }
    }
    return null
  }, [pending, targetLabel, writeWhere, steps, artifactDone, nextArtifactStep])

  const execute = async () => {
    if (!pending || !targetOk) return
    setBusy(true)
    setError(null)
    const modeRun = pending === 'full' ? 'full' : 'step'
    const step = pending === 'full' ? null : pending
    setPending(null)
    try {
      const { job: started } = await postRun({
        confirm: true,
        mode: modeRun,
        step,
        batch_id: batchId || null,
        project_id: projectId || null,
        framework: framework || '',
      })
      setJob(started)
      onJobChange?.(started)
      setLog('')
      await refreshJob(started.id)
    } catch (e) {
      setError(friendlyError(e))
    } finally {
      setBusy(false)
    }
  }

  if (!targetOk) {
    return (
      <p className="card-sub" style={{ margin: 0 }}>
        Select a project or upload a batch to enable runs.
      </p>
    )
  }

  return (
    <div className="ingest-run">
      <div className="ingest-mode-toggle" role="tablist" aria-label="Run mode">
        <button
          type="button"
          role="tab"
          aria-selected={mode === 'auto'}
          className={`ingest-mode-btn ${mode === 'auto' ? 'active' : ''}`}
          onClick={() => setMode('auto')}
          disabled={busy || running}
        >
          <span className="ingest-mode-kicker">Option A</span>
          <strong>Complete auto run</strong>
          <span>All stages in one confirmed job</span>
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={mode === 'stepwise'}
          className={`ingest-mode-btn ${mode === 'stepwise' ? 'active' : ''}`}
          onClick={() => setMode('stepwise')}
          disabled={busy || running}
        >
          <span className="ingest-mode-kicker">Option B</span>
          <strong>Run step by step</strong>
          <span>Confirm each stage before it runs</span>
        </button>
      </div>

      {mode === 'auto' ? (
        <div className="ingest-auto-panel">
          <div className="ingest-auto-copy">
            <h3>Complete auto run</h3>
            <p>
              Starts the full backend pipeline for <strong>{targetLabel}</strong> after one
              confirmation. If the machine stopped mid-run, finished stages are skipped and work
              continues from saved output (Normalize also resumes per lesson).
            </p>
          </div>
          <div className="ingest-auto-actions">
            <button
              type="button"
              className="btn primary"
              disabled={busy || running}
              onClick={() => setPending('full')}
            >
              {paused && job?.mode === 'full'
                ? 'Complete pipeline paused'
                : running && job?.mode === 'full'
                ? 'Running complete pipeline…'
                : artifactDone.length
                  ? 'Resume complete pipeline'
                  : 'Run complete pipeline'}
            </button>
            <JobPauseButton job={job} onChange={onPauseChange} />
            {logsPath ? (
              <Link className="btn" to={logsPath}>
                Open logs
              </Link>
            ) : null}
          </div>
        </div>
      ) : (
        <div className="ingest-stepwise">
          <div className="ingest-stepwise-head">
            <div>
              <h3>Run step by step</h3>
              <p>
                Confirm each stage for <strong>{targetLabel}</strong>. Finished stages (from output
                folders) stay Done; the next ready step is highlighted for approval.
              </p>
            </div>
            <div className="ingest-stepwise-pct">
              <span>{progressPct}%</span>
              <div className="ingest-stepwise-track">
                <div className="ingest-stepwise-fill" style={{ width: `${progressPct}%` }} />
              </div>
            </div>
          </div>

          <ol className="step-wizard">
            {steps.map((s, i) => {
              const done = doneIds.includes(s.id)
              const isNext = nextStep?.id === s.id
              const isActive = running && job?.current_step === s.id
              const failed = job?.status === 'failed' && job.current_step === s.id && !done
              let state: 'done' | 'active' | 'paused' | 'ready' | 'waiting' | 'failed' = 'waiting'
              if (done) state = 'done'
              else if (failed) state = 'failed'
              else if (isActive && paused) state = 'paused'
              else if (isActive) state = 'active'
              else if (isNext) state = 'ready'

              return (
                <li key={s.id} className={`step-wizard-item ${state}`}>
                  <div className="step-wizard-rail">
                    <span className="step-wizard-dot">{done ? '✓' : i + 1}</span>
                    {i < steps.length - 1 ? <span className="step-wizard-line" aria-hidden /> : null}
                  </div>
                  <div className="step-wizard-body">
                    <div className="step-wizard-top">
                      <div>
                        <strong>{s.name}</strong>
                        <p>{s.detail}</p>
                      </div>
                      <span
                        className={`badge ${statusClass(
                          state === 'done'
                            ? 'succeeded'
                            : state === 'failed'
                              ? 'failed'
                              : state === 'active'
                                ? 'running'
                                : state === 'paused'
                                  ? 'paused'
                                  : 'queued',
                        )}`}
                      >
                        {state === 'done'
                          ? 'Done'
                          : state === 'active'
                            ? 'Running'
                            : state === 'paused'
                              ? 'Paused'
                              : state === 'ready'
                              ? 'Ready'
                              : state === 'failed'
                                ? 'Failed'
                                : 'Waiting'}
                      </span>
                    </div>
                    {state === 'ready' ? (
                      <button
                        type="button"
                        className="btn primary"
                        disabled={busy || running}
                        onClick={() => setPending(s.id)}
                      >
                        Confirm & run this step
                      </button>
                    ) : null}
                    {state === 'failed' ? (
                      <button
                        type="button"
                        className="btn primary"
                        disabled={busy || running}
                        onClick={() => setPending(s.id)}
                      >
                        Retry this step
                      </button>
                    ) : null}
                  </div>
                </li>
              )
            })}
          </ol>

          <div className="ingest-stepwise-foot">
            <JobPauseButton job={job} onChange={onPauseChange} />
            {logsPath ? (
              <Link className="btn" to={logsPath}>
                Open logs
              </Link>
            ) : null}
            <button
              type="button"
              className="btn"
              disabled={busy || running}
              onClick={() => {
                if (
                  window.confirm(
                    'Clear this browser session’s step markers and re-read output folders?',
                  )
                ) {
                  setSessionDone([])
                  void syncArtifacts()
                }
              }}
            >
              Refresh progress
            </button>
            {!nextStep && doneIds.length === steps.length ? (
              <span className="none-ok" style={{ margin: 0 }}>
                All runnable steps have output for this project.
              </span>
            ) : null}
          </div>
        </div>
      )}

      {error ? <p className="none-error">{error}</p> : null}

      {job ? (
        <div className="pipe-job">
          <div className="pipe-job-top">
            <span className={`badge ${statusClass(job.status)}`}>
              {job.status}
              {typeof job.percent === 'number' ? ` · ${job.percent}%` : ''}
            </span>
            <code className="pipe-job-id">{job.id}</code>
            {job.current_step ? <span className="card-sub">step: {job.current_step}</span> : null}
          </div>
          {job.status === 'failed' || job.status === 'cancelled' ? (
            <div className="run-error" role="alert">
              <strong>{job.status === 'failed' ? 'Run failed' : 'Run stopped'}</strong>
              <span>{job.error || job.message || 'The run stopped without a message. Open logs for details.'}</span>
            </div>
          ) : job.message ? (
            <p className="pipe-job-msg">{job.message}</p>
          ) : null}
          {log ? (
            <pre className="pipe-log" tabIndex={0}>
              {log}
            </pre>
          ) : null}
        </div>
      ) : null}

      <ConfirmDialog
        open={Boolean(pending && dialogCopy)}
        title={dialogCopy?.title || ''}
        body={dialogCopy?.body || ''}
        confirmLabel={dialogCopy?.confirmLabel}
        busy={busy}
        onCancel={() => !busy && setPending(null)}
        onConfirm={() => void execute()}
      />
    </div>
  )
}
