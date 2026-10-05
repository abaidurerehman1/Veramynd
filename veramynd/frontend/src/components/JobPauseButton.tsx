import { useState } from 'react'
import { isJobActive } from '../lib/jobs'
import type { PipelineJob } from './LivePipelineProgress'

async function setPaused(jobId: string, pause: boolean): Promise<PipelineJob> {
  const res = await fetch(`/api/pipeline/jobs/${encodeURIComponent(jobId)}/${pause ? 'pause' : 'resume'}`, {
    method: 'POST',
    credentials: 'include',
  })
  const data = await res.json().catch(() => ({}))
  if (!res.ok) {
    const detail = data?.detail
    throw new Error(typeof detail === 'string' ? detail : `HTTP ${res.status}`)
  }
  return (data as { job: PipelineJob }).job
}

type Props = {
  job: PipelineJob | null
  onChange?: (job: PipelineJob) => void
  className?: string
}

/**
 * Pause / Resume for a live pipeline job. Pausing freezes the current stage where it is
 * and holds the next one; resuming continues from the same point.
 */
export function JobPauseButton({ job, onChange, className = '' }: Props) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  if (!job || !isJobActive(job.status)) return null

  const paused = job.status === 'paused'
  const toggle = async () => {
    setBusy(true)
    setError(null)
    try {
      onChange?.(await setPaused(job.id, !paused))
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(false)
    }
  }

  return (
    <span className={`job-pause ${className}`}>
      <button
        type="button"
        className={`btn job-pause-btn ${paused ? 'primary is-paused' : ''}`}
        disabled={busy}
        onClick={() => void toggle()}
        title={paused ? 'Continue the run from where it stopped' : 'Freeze the run; nothing is lost'}
      >
        <svg width="14" height="14" viewBox="0 0 24 24" aria-hidden="true">
          {paused ? (
            <path d="M7 5v14l12-7z" fill="currentColor" />
          ) : (
            <path d="M7 5h3.5v14H7zM13.5 5H17v14h-3.5z" fill="currentColor" />
          )}
        </svg>
        {busy ? (paused ? 'Resuming…' : 'Pausing…') : paused ? 'Resume run' : 'Pause run'}
      </button>
      {error ? (
        <span className="job-pause-error" role="alert">
          {error}
        </span>
      ) : null}
    </span>
  )
}
