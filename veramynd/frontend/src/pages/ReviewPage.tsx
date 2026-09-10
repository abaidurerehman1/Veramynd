import { useCallback, useEffect, useState } from 'react'
import { api, withProject } from '../api/client'
import type { AlignmentRow, ReviewItem } from '../api/types'
import { OverviewLoading } from '../components/OverviewStates'
import { useProject } from '../project/ProjectContext'

export function ReviewPage({
  reloadKey = 0,
  projectId,
}: {
  reloadKey?: number
  projectId: string
}) {
  const { project, loading: projectsLoading } = useProject()
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [rows, setRows] = useState<ReviewItem[]>([])
  const [selected, setSelected] = useState<AlignmentRow | null>(null)
  const [detailLoading, setDetailLoading] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const data = await api<{ rows: ReviewItem[] }>(withProject('/api/review', projectId))
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

  const openDetail = async (id: string) => {
    setDetailLoading(true)
    try {
      const row = await api<AlignmentRow>(
        withProject(`/api/alignments/${encodeURIComponent(id)}`, projectId),
      )
      setSelected(row)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setDetailLoading(false)
    }
  }

  if (projectsLoading || loading) return <OverviewLoading />

  if (error && !rows.length) {
    return (
      <div className="error-box">
        <h3>Unable to load Review</h3>
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
        <h1>Review</h1>
        <p>
          Results flagged for human verification
          {project?.name ? ` · ${project.name}` : ''}.
        </p>
      </div>

      <div className="kpi-grid kpi-4">
        <div className="kpi">
          <div className="label">In queue</div>
          <div className="value">{rows.length}</div>
          <div className="hint">Needs review</div>
        </div>
        <div className="kpi">
          <div className="label">Escalated</div>
          <div className="value">{rows.filter((r) => r.escalated).length}</div>
          <div className="hint">Higher scrutiny</div>
        </div>
        <div className="kpi">
          <div className="label">Low confidence</div>
          <div className="value">{rows.filter((r) => r.confidence === 'low').length}</div>
          <div className="hint">Confidence = low</div>
        </div>
        <div className="kpi">
          <div className="label">With evidence</div>
          <div className="value">{rows.filter((r) => Boolean(r.evidence)).length}</div>
          <div className="hint">Has quote</div>
        </div>
      </div>

      {rows.length === 0 ? (
        <section className="card">
          <div className="card-b">
            <p className="card-sub" style={{ margin: 0 }}>
              You&apos;re all caught up — no items currently flagged for review.
            </p>
          </div>
        </section>
      ) : (
        <div className="tile-grid">
          {rows.map((r) => (
            <article
              key={r.id}
              className="tile clickable"
              onClick={() => void openDetail(r.id)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' || e.key === ' ') {
                  e.preventDefault()
                  void openDetail(r.id)
                }
              }}
              role="button"
              tabIndex={0}
            >
              <div className="tile-top">
                <div className="tile-id">{r.resource_id}</div>
                <span className={`badge ${r.matched_status}`}>{r.matched_status}</span>
              </div>
              <div className="tile-meta">
                <div className="row">{r.lesson_title || 'Lesson'}</div>
                <div className="row">{r.standard_code}</div>
                <div className="row">
                  Confidence: {r.confidence || '—'}
                  {r.escalated ? ' · Escalated' : ''}
                </div>
                <div className="row">
                  {(r.review_reason || 'Needs review').slice(0, 100)}
                  {(r.review_reason || '').length > 100 ? '…' : ''}
                </div>
              </div>
              <div className="tile-foot">
                <div className="tile-price">
                  {r.evidence_page != null ? `p. ${r.evidence_page}` : 'Review'}
                </div>
                <button
                  type="button"
                  className="btn primary"
                  onClick={(e) => {
                    e.stopPropagation()
                    void openDetail(r.id)
                  }}
                >
                  Open review
                </button>
              </div>
              <p className="review-note">
                Approve / change / note are display-ready; write-back is disabled to protect
                production data.
              </p>
            </article>
          ))}
        </div>
      )}

      {selected || detailLoading ? (
        <div className="drawer">
          <button
            type="button"
            className="drawer-backdrop"
            aria-label="Close review detail"
            onClick={() => setSelected(null)}
          />
          <aside className="drawer-panel" role="dialog" aria-modal="true" aria-label="Review detail">
            <button type="button" className="btn ghost" onClick={() => setSelected(null)}>
              Close
            </button>
            {detailLoading && !selected ? (
              <p className="card-sub">Loading…</p>
            ) : selected ? (
              <>
                <h2 style={{ marginTop: 12 }}>
                  {selected.resource_id} → {selected.standard_code}
                </h2>
                <p style={{ color: 'var(--muted)', margin: '4px 0 12px' }}>{selected.lesson_title}</p>
                <div className="meta-grid">
                  <div className="cell">
                    <div className="k">Alignment</div>
                    <div className="v">
                      <span className={`badge ${selected.matched_status}`}>{selected.matched_status}</span>
                    </div>
                  </div>
                  <div className="cell">
                    <div className="k">Confidence</div>
                    <div className="v">{selected.confidence || '—'}</div>
                  </div>
                  <div className="cell">
                    <div className="k">Review</div>
                    <div className="v">{selected.needs_review ? 'Required' : 'No'}</div>
                  </div>
                  <div className="cell">
                    <div className="k">Escalated</div>
                    <div className="v">{selected.escalated ? 'Yes' : 'No'}</div>
                  </div>
                </div>
                <h3 className="lesson-subhead">Standard</h3>
                <p style={{ margin: 0, fontSize: 13, lineHeight: 1.5 }}>{selected.standard_text || '—'}</p>
                <h3 className="lesson-subhead">Evidence</h3>
                {selected.evidence ? (
                  <div className="evidence-quote">
                    {selected.evidence}
                    <div style={{ marginTop: 8, fontSize: 12, color: 'var(--muted)' }}>
                      Curriculum · p. {selected.evidence_page ?? '—'}
                    </div>
                  </div>
                ) : (
                  <p className="card-sub">No evidence quote.</p>
                )}
                <h3 className="lesson-subhead">Alignment reasoning</h3>
                <p style={{ margin: 0, fontSize: 13, color: '#374151' }}>{selected.rationale || '—'}</p>
                {selected.review_reason ? (
                  <>
                    <h3 className="lesson-subhead">Review reason</h3>
                    <p style={{ margin: 0, fontSize: 13 }}>{selected.review_reason}</p>
                  </>
                ) : null}
              </>
            ) : null}
          </aside>
        </div>
      ) : null}
    </div>
  )
}
