import { useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { ConfirmDialog } from './ConfirmDialog'
import { NONE_PROJECT_ID, useProject } from '../project/ProjectContext'
import type { ProjectCard } from '../api/types'

function statusLabel(p: ProjectCard) {
  const s = p.run_status || (p.has_output ? 'running' : 'empty')
  if (s === 'ready') return { text: 'Complete', cls: 'ok' }
  if (s === 'running') return { text: 'In progress', cls: 'info' }
  return { text: 'No output', cls: 'neutral' }
}

type Props = {
  /** Where “Open” navigates for a selected run. */
  openTo?: 'overview' | 'pipeline'
  title?: string
  subtitle?: string
}

export function ProjectsRunList({
  openTo = 'overview',
  title = 'Pipeline runs',
  subtitle,
}: Props) {
  const { projects, projectId, error, refreshProjects, clearProject } = useProject()
  const navigate = useNavigate()
  const [deleteTarget, setDeleteTarget] = useState<ProjectCard | null>(null)
  const [deletingId, setDeletingId] = useState<string | null>(null)
  const [actionError, setActionError] = useState<string | null>(null)

  const runs = useMemo(
    () => projects.filter((p) => p.has_output || p.run_status === 'ready' || p.run_status === 'running'),
    [projects],
  )

  const openRun = (id: string) => {
    localStorage.setItem('veramynd.activeProjectId', id)
    navigate(openTo === 'pipeline' ? `/projects/${id}/pipeline` : `/projects/${id}`)
  }

  const confirmDelete = async () => {
    if (!deleteTarget) return
    const id = deleteTarget.id
    setDeletingId(id)
    setActionError(null)
    try {
      const res = await fetch(`/api/projects/${encodeURIComponent(id)}`, { method: 'DELETE' })
      const text = await res.text()
      if (!res.ok) throw new Error(text || `HTTP ${res.status}`)
      setDeleteTarget(null)
      await refreshProjects()
      if (projectId === id) {
        clearProject()
        if (openTo === 'pipeline') {
          navigate(`/projects/${NONE_PROJECT_ID}/pipeline`)
        }
      }
    } catch (e) {
      setActionError(e instanceof Error ? e.message : String(e))
    } finally {
      setDeletingId(null)
    }
  }

  const countLabel = subtitle ?? `${runs.length} project${runs.length === 1 ? '' : 's'} with output`

  return (
    <>
      {(error || actionError) && (
        <p className="card-sub" role="alert" style={{ color: '#a84a3b', margin: '0 0 10px' }}>
          {actionError || error}
        </p>
      )}

      <section className="card">
        <div className="card-h">
          <div>
            <h2>{title}</h2>
            <p className="card-sub" style={{ margin: 0 }}>
              {countLabel}
            </p>
          </div>
        </div>
        <div className="card-b">
          {!runs.length ? (
            <p className="card-sub" style={{ margin: 0 }}>
              No completed runs yet. Upload on Ingestion, then run the pipeline — finished projects appear
              here.
            </p>
          ) : (
            <div className="projects-run-list">
              {runs.map((p) => {
                const badge = statusLabel(p)
                const meta = [
                  p.publisher,
                  p.grade != null ? `Grade ${p.grade}` : null,
                  p.subject,
                  p.module,
                  p.framework,
                ]
                  .filter(Boolean)
                  .join(' · ')
                const active = p.id === projectId
                return (
                  <article
                    className={`projects-run-card${active ? ' selected' : ''}`}
                    key={p.id}
                  >
                    <div className="projects-run-main">
                      <div className="projects-run-kicker">
                        <span className={`badge ${badge.cls}`}>{badge.text}</span>
                        {p.source === 'upload' ? (
                          <span className="badge neutral">Upload</span>
                        ) : (
                          <span className="badge neutral">Registry</span>
                        )}
                        {active ? <span className="badge info">Active</span> : null}
                        {p.is_default ? <span className="badge info">Default</span> : null}
                      </div>
                      <h3 className="projects-run-title">{p.name}</h3>
                      {meta ? <p className="card-sub">{meta}</p> : null}
                      <p className="projects-run-id" title={p.id}>
                        {p.id}
                      </p>
                    </div>
                    <div className="projects-run-actions">
                      <button
                        type="button"
                        className="btn outline-green"
                        onClick={() => openRun(p.id)}
                      >
                        {active && openTo === 'pipeline' ? 'Selected' : 'Open'}
                      </button>
                      <button
                        type="button"
                        className="btn danger-ghost"
                        disabled={deletingId === p.id}
                        onClick={() => setDeleteTarget(p)}
                      >
                        Delete
                      </button>
                    </div>
                  </article>
                )
              })}
            </div>
          )}
        </div>
      </section>

      <ConfirmDialog
        open={Boolean(deleteTarget)}
        title="Delete project?"
        body={
          deleteTarget
            ? deleteTarget.source === 'upload'
              ? `Permanently delete “${deleteTarget.name}” and its uploaded files / pipeline output? Job logs on the Logging page are kept until you Clear logs.`
              : `Remove “${deleteTarget.name}” from the project list? Registry projects keep on-disk artifacts; Logging is unchanged until you Clear logs.`
            : ''
        }
        confirmLabel="Delete project"
        danger
        busy={Boolean(deletingId)}
        onCancel={() => !deletingId && setDeleteTarget(null)}
        onConfirm={() => void confirmDelete()}
      />
    </>
  )
}
