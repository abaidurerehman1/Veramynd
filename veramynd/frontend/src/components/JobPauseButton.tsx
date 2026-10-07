import { useState } from 'react'
import { isJobActive } from '../lib/jobs'
import type { PipelineJob } from './LivePipelineProgress'
import { detailMessage, friendlyError } from '../lib/errors'
import { ConfirmDialog } from './ConfirmDialog'

async function jobAction(jobId: string, action: 'pause' | 'resume' | 'cancel'): Promise<PipelineJob> {
  const res = await fetch(`/api/pipeline/jobs/${encodeURIComponent(jobId)}/${action}`, {
    method: 'POST',
    credentials: 'include',
  })
  const data = await res.json().catch(() => ({}))
  if (!res.ok) {
    throw new Error(detailMessage(data, res.status))
  }
  return (data as { job: PipelineJob }).job
}

type Props = {
  job: PipelineJob | null
  onChange?: (job: PipelineJob) => void
  className?: string
}

/**
 * Pause / Resume and Stop for a live pipeline job. Pausing freezes the current stage where it is
 * and holds the next one; resuming continues from the same point; stopping ends the run (finished
 * stages stay on disk, so starting again continues from saved output).
 */
export function JobPauseButton({ job, onChange, className = '' }: Props) {
  const [busy, setBusy] = useState<'pause' | 'stop' | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [confirmStop, setConfirmStop] = useState(false)
  if (!job || !isJobActive(job.status)) return null

  const paused = job.status === 'paused'
  const toggle = async () => {
    setBusy('pause')
    setError(null)
    try {
      onChange?.(await jobAction(job.id, paused ? 'resume' : 'pause'))
    } catch (e) {
      setError(friendlyError(e))
    } finally {
      setBusy(null)
    }
  }
  const stop = async () => {
    setBusy('stop')
    setError(null)
    try {
      onChange?.(await jobAction(job.id, 'cancel'))
      setConfirmStop(false)
    } catch (e) {
      setError(friendlyError(e))
      setConfirmStop(false)
    } finally {
      setBusy(null)
    }
  }

  return (
    <span className={`job-pause ${className}`}>
      <button
        type="button"
        className={`btn job-pause-btn ${paused ? 'primary is-paused' : ''}`}
        disabled={busy !== null}
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
        {busy === 'pause' ? (paused ? 'Resuming…' : 'Pausing…') : paused ? 'Resume run' : 'Pause run'}
      </button>
      <button
        type="button"
        className="btn job-stop-btn"
        disabled={busy !== null}
        onClick={() => setConfirmStop(true)}
        title="End this run. Finished stages are kept."
      >
        <svg width="12" height="12" viewBox="0 0 24 24" aria-hidden="true">
          <rect x="5" y="5" width="14" height="14" rx="2" fill="currentColor" />
        </svg>
        {busy === 'stop' ? 'Stopping…' : 'Stop run'}
      </button>
      {error ? (
        <span className="job-pause-error" role="alert">
          {error}
        </span>
      ) : null}
      <ConfirmDialog
        open={confirmStop}
        title="Stop this run?"
        body={
          'The current stage is ended now and the next stages will not start. Stages and lessons that ' +
          'already finished are kept, so starting the run again continues from saved output.'
        }
        confirmLabel="Stop run"
        danger
        busy={busy === 'stop'}
        onCancel={() => busy === null && setConfirmStop(false)}
        onConfirm={() => void stop()}
      />
    </span>
  )
}
