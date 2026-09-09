import { useCallback, useEffect, useState } from 'react'
import { api, withProject } from '../api/client'
import { OverviewLoading } from '../components/OverviewStates'
import { NONE_PROJECT_ID, useProject } from '../project/ProjectContext'

type Health = {
  ok: boolean
  error?: string | null
  project_id?: string
  default_project_id?: string
  lessons?: number
  alignments?: number
}

export function SettingsPage({
  reloadKey = 0,
  onReload,
}: {
  reloadKey?: number
  onReload?: () => void | Promise<void>
}) {
  const { project, projectId, hasProject, refreshProjects } = useProject()
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState<string | null>(null)
  const [health, setHealth] = useState<Health | null>(null)
  const [reloading, setReloading] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const path =
        hasProject && projectId !== NONE_PROJECT_ID
          ? withProject('/api/health', projectId)
          : '/api/health'
      const data = await api<Health>(path)
      setHealth(data)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
      setHealth(null)
    } finally {
      setLoading(false)
    }
  }, [hasProject, projectId])

  useEffect(() => {
    void load()
  }, [load, reloadKey])

  const reloadCatalog = async () => {
    setReloading(true)
    setError(null)
    setSuccess(null)
    try {
      if (onReload) {
        await onReload()
      } else {
        const q =
          hasProject && projectId !== NONE_PROJECT_ID
            ? `?project_id=${encodeURIComponent(projectId)}`
            : ''
        const res = await fetch(`/api/reload${q}`, { method: 'POST' })
        if (!res.ok) throw new Error((await res.text()) || `HTTP ${res.status}`)
      }
      await refreshProjects()
      await load()
      setSuccess('Catalog reloaded successfully.')
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setReloading(false)
    }
  }

  if (loading && !health) return <OverviewLoading />

  return (
    <div className="analytics">
      <div className="page-header">
        <div>
          <h1>Settings</h1>
          <p>Workspace health and catalog reload for the active project.</p>
        </div>
      </div>

      {error ? (
        <p className="card-sub" role="alert" style={{ color: 'var(--bad)', margin: 0 }}>
          {error}
        </p>
      ) : null}
      {success ? (
        <p className="card-sub" role="status" style={{ color: 'var(--ok)', margin: 0 }}>
          {success}
        </p>
      ) : null}

      <div className="tile-grid" style={{ gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))' }}>
        <article className="tile">
          <div className="tile-top">
            <div className="tile-id">Active project</div>
            <span className={`badge ${hasProject ? 'ok' : 'neutral'}`}>
              {hasProject ? 'Selected' : 'None'}
            </span>
          </div>
          <div className="tile-meta">
            <div className="row">{hasProject ? project?.name || projectId : 'No project selected'}</div>
            {hasProject ? <div className="row path-row">{projectId}</div> : null}
          </div>
        </article>

        <article className="tile">
          <div className="tile-top">
            <div className="tile-id">Catalog health</div>
            <span className={`badge ${health?.ok ? 'ok' : 'warn'}`}>
              {health?.ok ? 'OK' : 'Issue'}
            </span>
          </div>
          <div className="tile-meta">
            <div className="row">Lessons: {health?.lessons ?? '—'}</div>
            <div className="row">Alignments: {health?.alignments ?? '—'}</div>
            {health?.error ? <div className="row">{health.error}</div> : null}
          </div>
          <div className="tile-foot">
            <span className="tile-price">Catalog</span>
            <button
              type="button"
              className="btn primary"
              disabled={reloading}
              onClick={() => void reloadCatalog()}
            >
              {reloading ? 'Reloading…' : 'Reload catalog'}
            </button>
          </div>
        </article>

        <article className="tile">
          <div className="tile-top">
            <div className="tile-id">Dashboard</div>
            <span className="badge info">Local</span>
          </div>
          <div className="tile-meta">
            <div className="row">Local workspace dashboard (API + React UI)</div>
            <div className="row">No authentication — keep private / VPN only</div>
          </div>
        </article>
      </div>
    </div>
  )
}
