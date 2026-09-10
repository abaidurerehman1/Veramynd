import { useCallback, useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { api, withProject } from '../api/client'
import type { LessonDetail } from '../api/types'
import { OverviewLoading } from '../components/OverviewStates'
import { useProject } from '../project/ProjectContext'

function asText(item: unknown): string {
  if (typeof item === 'string') return item
  if (item && typeof item === 'object') {
    const o = item as Record<string, unknown>
    return String(o.term || o.text || o.title || JSON.stringify(item))
  }
  return String(item ?? '')
}

export function LessonPage({ reloadKey = 0 }: { reloadKey?: number }) {
  const { projectId = '', lessonCode = '' } = useParams()
  const { project } = useProject()
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [lesson, setLesson] = useState<LessonDetail | null>(null)

  const load = useCallback(async () => {
    if (!projectId || !lessonCode) return
    setLoading(true)
    setError(null)
    try {
      const data = await api<LessonDetail>(
        withProject(`/api/lessons/${encodeURIComponent(lessonCode)}`, projectId),
      )
      setLesson(data)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
      setLesson(null)
    } finally {
      setLoading(false)
    }
  }, [projectId, lessonCode])

  useEffect(() => {
    void load()
  }, [load, reloadKey])

  if (loading) return <OverviewLoading />

  if (error || !lesson) {
    return (
      <div className="error-box">
        <h3>Unable to load lesson</h3>
        <p>{error || 'Not found'}</p>
        <Link className="btn" to={`/projects/${projectId}/curriculum`}>
          Back to Curriculum
        </Link>
      </div>
    )
  }

  const summary = lesson.alignments_summary || {}
  const curriculumTo = `/projects/${projectId}/curriculum`

  return (
    <div className="analytics">
      <div className="page-header">
        <p className="card-sub" style={{ margin: '0 0 6px' }}>
          <Link to={curriculumTo}>Curriculum</Link>
          {' · '}
          {project?.name || projectId}
        </p>
        <h1>{lesson.title || lesson.code}</h1>
        <p>
          {lesson.code}
          {lesson.page_start != null || lesson.page_end != null
            ? ` · Pages ${lesson.page_start ?? '—'}–${lesson.page_end ?? '—'}`
            : ''}
          {lesson.unit != null ? ` · Unit ${lesson.unit}` : ''}
          {lesson.lesson != null ? ` · Lesson ${lesson.lesson}` : ''}
        </p>
      </div>

      <div className="kpi-grid kpi-4">
        <div className="kpi">
          <div className="label">Full</div>
          <div className="value">{summary.full || 0}</div>
        </div>
        <div className="kpi">
          <div className="label">Partial</div>
          <div className="value">{summary.partial || 0}</div>
        </div>
        <div className="kpi">
          <div className="label">None</div>
          <div className="value">{summary.none || 0}</div>
        </div>
        <div className="kpi">
          <div className="label">Review</div>
          <div className="value">{summary.review || 0}</div>
        </div>
      </div>

      <div className="grid-2">
        <section className="card">
          <div className="card-h">
            <h2>Instructional structure</h2>
          </div>
          <div className="card-b">
            {(lesson.instructional_blocks || []).length === 0 ? (
              <p className="card-sub" style={{ margin: 0 }}>
                No instructional blocks in Stage-1 for this lesson.
              </p>
            ) : (
              (lesson.instructional_blocks || []).map((b, i) => {
                const block = b as Record<string, unknown>
                const steps = Array.isArray(block.steps) ? block.steps.length : 0
                return (
                  <div className="lesson-block" key={i}>
                    <strong>
                      {String(block.section || '')} {String(block.letter || '')}
                    </strong>
                    {block.title ? ` — ${String(block.title)}` : ''}
                    <div className="card-sub">
                      p. {block.page != null ? String(block.page) : '—'} · {steps} steps
                    </div>
                  </div>
                )
              })
            )}
          </div>
        </section>

        <section className="card">
          <div className="card-h">
            <h2>Materials &amp; vocabulary</h2>
          </div>
          <div className="card-b">
            <h3 className="lesson-subhead">Materials</h3>
            <ul className="lesson-list">
              {(lesson.materials || []).slice(0, 12).map((m, i) => (
                <li key={i}>{asText(m)}</li>
              ))}
            </ul>
            <h3 className="lesson-subhead">Vocabulary</h3>
            <ul className="lesson-list">
              {(lesson.vocabulary || []).slice(0, 12).map((m, i) => (
                <li key={i}>{asText(m)}</li>
              ))}
            </ul>
          </div>
        </section>
      </div>
    </div>
  )
}
