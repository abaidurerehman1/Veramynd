import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api, withProject } from '../api/client'
import { OverviewLoading } from '../components/OverviewStates'
import { NONE_PROJECT_ID, useProject } from '../project/ProjectContext'

type ExportItem = {
  id: string
  name: string
  type: string
  path: string
  available: boolean
  download_url: string | null
}

export function ExportsPage({
  reloadKey = 0,
  projectId,
}: {
  reloadKey?: number
  projectId: string
}) {
  const { project, hasProject, loading: projectsLoading } = useProject()
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [rows, setRows] = useState<ExportItem[]>([])

  const load = useCallback(async () => {
    if (!hasProject) {
      setRows([])
      setLoading(false)
      return
    }
    setLoading(true)
    setError(null)
    try {
      const data = await api<{ rows: ExportItem[] }>(withProject('/api/exports', projectId))
      setRows(data.rows || [])
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
      setRows([])
    } finally {
      setLoading(false)
    }
  }, [hasProject, projectId])

  useEffect(() => {
    void load()
  }, [load, reloadKey])

  if (projectsLoading || loading) return <OverviewLoading />

  if (!hasProject) {
    return (
      <div className="analytics">
        <div className="page-header">
          <h1>Exports</h1>
          <p>Download client packages and evaluation artifacts.</p>
        </div>
        <section className="card">
          <div className="card-b">
            <p className="card-sub" style={{ margin: 0 }}>
              Select a project with pipeline output to download exports.{' '}
              <Link to={`/projects/${NONE_PROJECT_ID}/projects`}>Browse projects</Link>
            </p>
          </div>
        </section>
      </div>
    )
  }

  if (error && !rows.length) {
    return (
      <div className="error-box">
        <h3>Unable to load Exports</h3>
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
          <h1>Exports</h1>
          <p>
            Download client packages and evaluation artifacts
            {project?.name ? ` · ${project.name}` : ''}.
          </p>
        </div>
      </div>

      <div className="tile-grid">
        {rows.map((e) => (
          <article className="tile" key={e.id}>
            <div className="tile-top">
              <div className="tile-id">{e.name}</div>
              <span className={`badge ${e.available ? 'ok' : 'neutral'}`}>
                {e.available ? 'Ready' : 'Missing'}
              </span>
            </div>
            <div className="tile-meta">
              <div className="row">Type: {e.type}</div>
              {e.path ? <div className="row path-row">{e.path}</div> : null}
            </div>
            <div className="tile-foot">
              <span className="tile-price">{e.available ? 'Available' : 'Not generated'}</span>
              {e.download_url ? (
                <a className="btn primary" href={e.download_url}>
                  Download
                </a>
              ) : (
                <span className="btn" style={{ opacity: 0.5, pointerEvents: 'none' }}>
                  Unavailable
                </span>
              )}
            </div>
          </article>
        ))}
      </div>
    </div>
  )
}
