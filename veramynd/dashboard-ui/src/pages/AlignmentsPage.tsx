import { useCallback, useEffect, useState } from 'react'
import { api, withProject } from '../api/client'
import type { AlignmentRow, OverviewMetrics } from '../api/types'
import { OverviewLoading } from '../components/OverviewStates'
import { useProject } from '../project/ProjectContext'

type StatusFilter = '' | 'full' | 'partial' | 'none' | '__review__'

function actionLabel(a: AlignmentRow): string {
  if (a.needs_review) return 'Open review'
  if (a.matched_status === 'full') return 'View evidence'
  if (a.matched_status === 'partial') return 'Inspect partial'
  return 'View details'
}

export function AlignmentsPage({
  reloadKey = 0,
  projectId,
}: {
  reloadKey?: number
  projectId: string
}) {
  const { project, loading: projectsLoading } = useProject()
  const [bootLoading, setBootLoading] = useState(true)
  const [listLoading, setListLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [overview, setOverview] = useState<OverviewMetrics | null>(null)
  const [rows, setRows] = useState<AlignmentRow[]>([])
  const [total, setTotal] = useState(0)
  const [status, setStatus] = useState<StatusFilter>('')
  const [query, setQuery] = useState('')
  const [searchInput, setSearchInput] = useState('')
  const [selected, setSelected] = useState<AlignmentRow | null>(null)
  const [detailLoading, setDetailLoading] = useState(false)

  const loadOverview = useCallback(async () => {
    setBootLoading(true)
    setError(null)
    try {
      const ov = await api<OverviewMetrics>(withProject('/api/overview', projectId))
      setOverview(ov)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
      setOverview(null)
    } finally {
      setBootLoading(false)
    }
  }, [projectId])

  const loadRows = useCallback(async () => {
    setListLoading(true)
    setError(null)
    try {
      const params = new URLSearchParams({ limit: '60' })
      if (query) params.set('q', query)
      if (status === '__review__') params.set('needs_review', 'true')
      else if (status) params.set('status', status)
      const path = withProject(`/api/alignments?${params}`, projectId)
      const data = await api<{ rows: AlignmentRow[]; total: number }>(path)
      setRows(data.rows || [])
      setTotal(data.total || 0)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
      setRows([])
      setTotal(0)
    } finally {
      setListLoading(false)
    }
  }, [projectId, query, status])

  useEffect(() => {
    void loadOverview()
  }, [loadOverview, reloadKey])

  useEffect(() => {
    void loadRows()
  }, [loadRows, reloadKey])

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

  if (projectsLoading || bootLoading) return <OverviewLoading />

  const by = overview?.by_status || {}

  return (
    <div className="analytics">
      <div className="page-header">
        <h1>Alignments</h1>
        <p>Browse lesson–standard evaluations for {project?.name || projectId}.</p>
      </div>

      <div className="filter-tabs" role="tablist" aria-label="Alignment status">
        {(
          [
            { id: '' as StatusFilter, label: 'All', count: overview?.alignments ?? 0, tone: 'all' },
            { id: 'full' as StatusFilter, label: 'Full', count: by.full || 0, tone: 'full' },
            { id: 'partial' as StatusFilter, label: 'Partial', count: by.partial || 0, tone: 'partial' },
            { id: 'none' as StatusFilter, label: 'None', count: by.none || 0, tone: 'none' },
            {
              id: '__review__' as StatusFilter,
              label: 'Review',
              count: overview?.review_required || 0,
              tone: 'review',
            },
          ] as const
        ).map((tab) => (
          <button
            key={tab.id || 'all'}
            type="button"
            className={`filter-tab${status === tab.id ? ' active' : ''}`}
            data-tone={tab.tone}
            onClick={() => setStatus(tab.id)}
          >
            {tab.label} <span className="count">{tab.count}</span>
          </button>
        ))}
      </div>

      <div className="filters">
        <input
          value={searchInput}
          onChange={(e) => setSearchInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter') setQuery(searchInput.trim())
          }}
          placeholder="Search lessons, standards, evidence…"
          aria-label="Search alignments"
        />
        <button type="button" className="btn" onClick={() => setQuery(searchInput.trim())}>
          Search
        </button>
      </div>

      {error && !rows.length ? (
        <div className="error-box">
          <h3>Unable to load Alignments</h3>
          <p>{error}</p>
          <button type="button" className="btn" onClick={() => void loadRows()}>
            Retry
          </button>
        </div>
      ) : listLoading && !rows.length ? (
        <OverviewLoading />
      ) : rows.length === 0 ? (
        <section className="card">
          <div className="card-b">
            <p className="card-sub" style={{ margin: 0 }}>
              No alignments match. Try another filter or clear search.
            </p>
          </div>
        </section>
      ) : (
        <>
          <div className={`tile-grid${listLoading ? ' is-loading' : ''}`}>
            {rows.map((a) => (
              <article
                key={a.id}
                className="tile clickable"
                onClick={() => void openDetail(a.id)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault()
                    void openDetail(a.id)
                  }
                }}
                role="button"
                tabIndex={0}
              >
                <div className="tile-top">
                  <div className="tile-id">{a.resource_id}</div>
                  <span className={`badge ${a.matched_status}`}>{a.matched_status}</span>
                </div>
                <div className="tile-meta">
                  <div className="row">{a.lesson_title || 'Lesson'}</div>
                  <div className="row">{a.standard_code}</div>
                  <div className="row">
                    Confidence: {a.confidence || '—'}
                    {a.needs_review ? ' · Needs review' : ''}
                  </div>
                </div>
                <div className="tile-foot">
                  <div className="tile-price">
                    {a.evidence_page != null ? `p. ${a.evidence_page}` : '—'}
                  </div>
                  <button
                    type="button"
                    className={`btn ${a.matched_status === 'full' ? 'primary' : 'outline-green'}`}
                    onClick={(e) => {
                      e.stopPropagation()
                      void openDetail(a.id)
                    }}
                  >
                    {actionLabel(a)}
                  </button>
                </div>
              </article>
            ))}
          </div>
          <p className="std-showing">
            Showing {rows.length} of {total}
            {listLoading ? ' · Updating…' : ''}
          </p>
        </>
      )}

      {selected || detailLoading ? (
        <div className="drawer">
          <button
            type="button"
            className="drawer-backdrop"
            aria-label="Close alignment detail"
            onClick={() => setSelected(null)}
          />
          <aside className="drawer-panel" role="dialog" aria-modal="true" aria-label="Alignment detail">
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
                    <div className="k">Grounded</div>
                    <div className="v">{selected.grounded ? 'Yes' : 'No'}</div>
                  </div>
                  <div className="cell">
                    <div className="k">Review</div>
                    <div className="v">{selected.needs_review ? 'Required' : 'No'}</div>
                  </div>
                </div>
                <h3 className="lesson-subhead">Standard</h3>
                <p style={{ margin: 0, fontSize: 13, lineHeight: 1.5 }}>{selected.standard_text || '—'}</p>
                <h3 className="lesson-subhead">Evidence</h3>
                {selected.evidence ? (
                  <div className="evidence-quote">
                    {selected.evidence}
                    <div style={{ marginTop: 8, fontSize: 12, color: 'var(--muted)' }}>
                      Teacher Guide · p. {selected.evidence_page ?? '—'}
                    </div>
                  </div>
                ) : (
                  <p className="card-sub">No evidence quote.</p>
                )}
                <h3 className="lesson-subhead">Alignment reasoning</h3>
                <p style={{ margin: 0, fontSize: 13, color: '#374151' }}>{selected.rationale || '—'}</p>
                {(selected.clauses || []).length > 0 ? (
                  <>
                    <h3 className="lesson-subhead">Clauses</h3>
                    <ul className="lesson-list">
                      {selected.clauses!.map((c, i) => {
                        const clause = c as { met?: boolean; clause?: string; note?: string }
                        return (
                          <li key={i}>
                            <strong>{clause.met ? 'Met' : 'Unmet'}:</strong> {clause.clause || ''}
                            {clause.note ? (
                              <div style={{ color: 'var(--muted)', marginTop: 2 }}>{clause.note}</div>
                            ) : null}
                          </li>
                        )
                      })}
                    </ul>
                  </>
                ) : null}
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
