import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { api, withProject } from '../api/client'
import type { LessonCoverageRow } from '../api/types'
import { OverviewLoading } from '../components/OverviewStates'
import { lessonMeta } from '../lib/format'
import { useProject } from '../project/ProjectContext'

function lessonStatus(row: LessonCoverageRow): 'full' | 'partial' | 'review' | 'none' {
  if (row.review > 0) return 'review'
  if (row.full > 0) return 'full'
  if (row.partial > 0) return 'partial'
  return 'none'
}

export function CurriculumPage({
  reloadKey = 0,
  projectId,
}: {
  reloadKey?: number
  projectId: string
}) {
  const { project, loading: projectsLoading } = useProject()
  const navigate = useNavigate()
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [rows, setRows] = useState<LessonCoverageRow[]>([])

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const data = await api<{ rows: LessonCoverageRow[] }>(
        withProject('/api/lessons/coverage', projectId),
      )
      setRows(data.rows || [])
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
      setRows([])
    } finally {
      setLoading(false)
    }
  }, [projectId])

  useEffect(() => {
    void load()
  }, [load, reloadKey])

  const sorted = useMemo(
    () =>
      [...rows]
        .map((row) => ({ ...row, meta: lessonMeta(row.resource_id) }))
        .sort((a, b) => a.meta.unit - b.meta.unit || a.meta.lesson - b.meta.lesson),
    [rows],
  )

  if (projectsLoading || loading) return <OverviewLoading />

  if (error) {
    return (
      <div className="error-box">
        <h3>Unable to load Curriculum</h3>
        <p>{error}</p>
        <button type="button" className="btn" onClick={() => void load()}>
          Retry
        </button>
      </div>
    )
  }

  const pdfLabel =
    project?.inputs?.guide_pdf?.replace(/\\/g, '/').split('/').pop() ||
    project?.name ||
    'Curriculum PDF'

  return (
    <div className="analytics">
      <div className="page-header">
        <h1>Curriculum</h1>
        <p>Lessons from this project&apos;s PDF, loaded from pipeline output.</p>
      </div>

      <section className="card">
        <div className="card-b curriculum-summary">
          <div>
            <h2 className="curriculum-title">{project?.name || projectId}</h2>
            <p className="card-sub">
              {[project?.publisher, project?.grade != null ? `Grade ${project.grade}` : null, project?.subject, project?.module]
                .filter(Boolean)
                .join(' · ')}
            </p>
            <p className="card-sub curriculum-pdf" title={project?.inputs?.guide_pdf}>
              {pdfLabel}
            </p>
          </div>
          <div className="curriculum-count">
            <strong>{sorted.length}</strong>
            <span>lessons</span>
          </div>
        </div>
      </section>

      {sorted.length === 0 ? (
        <section className="card">
          <div className="card-b">
            <p className="card-sub" style={{ margin: 0 }}>
              No lessons yet. Run the pipeline for this PDF + XLSX, then refresh.
            </p>
          </div>
        </section>
      ) : (
        <div className="tile-grid">
          {sorted.map((row) => {
            const status = lessonStatus(row)
            const to = `/projects/${projectId}/curriculum/${encodeURIComponent(row.resource_id)}`
            return (
              <article
                key={row.resource_id}
                className="tile clickable"
                onClick={() => navigate(to)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault()
                    navigate(to)
                  }
                }}
                role="link"
                tabIndex={0}
              >
                <div className="tile-top">
                  <div className="tile-id">{row.meta.short}</div>
                  <span className={`badge ${status}`}>{status}</span>
                </div>
                <div className="tile-meta">
                  <div className="row">{row.title || row.resource_id}</div>
                  <div className="row">
                    Full {row.full} · Partial {row.partial} · None {row.none}
                    {row.review ? ` · Review ${row.review}` : ''}
                  </div>
                </div>
                <div className="tile-foot">
                  <div className="tile-price">{row.aligned} aligned</div>
                  <Link
                    className="btn primary"
                    to={to}
                    onClick={(e) => e.stopPropagation()}
                  >
                    Open lesson
                  </Link>
                </div>
              </article>
            )
          })}
        </div>
      )}
    </div>
  )
}
