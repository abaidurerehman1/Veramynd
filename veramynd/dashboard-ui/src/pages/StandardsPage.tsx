import { useCallback, useEffect, useMemo, useState } from 'react'
import { api, withProject } from '../api/client'
import type { StandardCoverageRow, StandardNode } from '../api/types'
import { OverviewLoading } from '../components/OverviewStates'
import { useProject } from '../project/ProjectContext'

type FilterStatus = '' | 'covered' | 'partial' | 'not_found' | 'review'

function statusBadgeClass(status: string): string {
  if (status === 'covered') return 'full'
  if (status === 'partial') return 'partial'
  if (status === 'review') return 'review'
  if (status === 'not_found') return 'none'
  return 'neutral'
}

function StandardTreeNode({ node }: { node: StandardNode }) {
  const open = node.level === 'domain'
  return (
    <details className="std-node" open={open || undefined}>
      <summary>
        <strong>{node.code}</strong>
        {node.label ? ` — ${node.label}` : ''}
      </summary>
      {node.text ? <div className="node-text">{node.text.slice(0, 180)}</div> : null}
      {(node.children || []).map((child) => (
        <StandardTreeNode key={child.code} node={child} />
      ))}
    </details>
  )
}

export function StandardsPage({
  reloadKey = 0,
  projectId,
}: {
  reloadKey?: number
  projectId: string
}) {
  const { project, loading: projectsLoading } = useProject()
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [rows, setRows] = useState<StandardCoverageRow[]>([])
  const [roots, setRoots] = useState<StandardNode[]>([])
  const [filter, setFilter] = useState<FilterStatus>('')

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const [cov, tree] = await Promise.all([
        api<{ rows: StandardCoverageRow[] }>(withProject('/api/standards/coverage', projectId)),
        api<{ roots: StandardNode[] }>(withProject('/api/standards/tree', projectId)),
      ])
      setRows(cov.rows || [])
      setRoots(tree.roots || [])
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
      setRows([])
      setRoots([])
    } finally {
      setLoading(false)
    }
  }, [projectId])

  useEffect(() => {
    void load()
  }, [load, reloadKey])

  const counts = useMemo(() => {
    const c = { covered: 0, partial: 0, not_found: 0, review: 0 }
    for (const r of rows) {
      if (r.status in c) c[r.status as keyof typeof c] += 1
    }
    return c
  }, [rows])

  const filtered = useMemo(
    () => (filter ? rows.filter((r) => r.status === filter) : rows),
    [rows, filter],
  )
  const slice = filtered.slice(0, 90)

  if (projectsLoading || loading) return <OverviewLoading />

  if (error) {
    return (
      <div className="error-box">
        <h3>Unable to load Standards</h3>
        <p>{error}</p>
        <button type="button" className="btn" onClick={() => void load()}>
          Retry
        </button>
      </div>
    )
  }

  const xlsxLabel =
    project?.inputs?.standards_xlsx?.replace(/\\/g, '/').split('/').pop() ||
    project?.framework ||
    'Standards workbook'

  return (
    <div className="analytics">
      <div className="page-header">
        <h1>Standards</h1>
        <p>
          {project?.framework || 'Standards'} hierarchy and coverage for this project.
        </p>
      </div>

      <section className="card">
        <div className="card-b curriculum-summary">
          <div>
            <h2 className="curriculum-title">{project?.name || projectId}</h2>
            <p className="card-sub">
              {[project?.framework, project?.grade != null ? `Grade ${project.grade}` : null]
                .filter(Boolean)
                .join(' · ')}
            </p>
            <p className="card-sub curriculum-pdf" title={project?.inputs?.standards_xlsx}>
              {xlsxLabel}
            </p>
          </div>
          <div className="curriculum-count">
            <strong>{rows.length}</strong>
            <span>standards</span>
          </div>
        </div>
      </section>

      <div className="filter-tabs" role="tablist" aria-label="Coverage filter">
        {(
          [
            { status: '' as FilterStatus, label: 'All', count: rows.length, tone: 'all' },
            { status: 'covered' as FilterStatus, label: 'Covered', count: counts.covered, tone: 'full' },
            { status: 'partial' as FilterStatus, label: 'Partial', count: counts.partial, tone: 'partial' },
            { status: 'not_found' as FilterStatus, label: 'Not found', count: counts.not_found, tone: 'none' },
            { status: 'review' as FilterStatus, label: 'Review', count: counts.review, tone: 'review' },
          ] as const
        ).map((tab) => (
          <button
            key={tab.status || 'all'}
            type="button"
            className={`filter-tab${filter === tab.status ? ' active' : ''}`}
            data-tone={tab.tone}
            onClick={() => setFilter(tab.status)}
          >
            {tab.label} <span className="count">{tab.count}</span>
          </button>
        ))}
      </div>

      {slice.length === 0 ? (
        <section className="card">
          <div className="card-b">
            <p className="card-sub" style={{ margin: 0 }}>
              {rows.length === 0
                ? 'No standards yet. Run the pipeline for this PDF + XLSX, then refresh.'
                : 'No standards in this filter. Try another coverage status.'}
            </p>
          </div>
        </section>
      ) : (
        <>
          <div className="tile-grid">
            {slice.map((r) => (
              <article className="tile" key={r.code}>
                <div className="tile-top">
                  <div className="tile-id">{r.code}</div>
                  <span className={`badge ${statusBadgeClass(r.status)}`}>{r.status.replace('_', ' ')}</span>
                </div>
                <div className="tile-meta">
                  <div className="row">{(r.text || r.label || '—').slice(0, 120)}</div>
                  <div className="row">
                    {r.level ? `${r.level} · ` : ''}
                    {r.lessons.length} lesson{r.lessons.length === 1 ? '' : 's'}
                    {r.full || r.partial
                      ? ` · Full ${r.full} / Partial ${r.partial}`
                      : ''}
                  </div>
                </div>
                <div className="tile-foot">
                  <div className="tile-price">{r.status.replace('_', ' ')}</div>
                </div>
              </article>
            ))}
          </div>
          <p className="std-showing">
            Showing {slice.length} of {filtered.length}
          </p>
        </>
      )}

      <section className="card" style={{ marginTop: 18 }}>
        <div className="card-h">
          <h2>Hierarchy</h2>
        </div>
        <div className="card-b tree std-tree">
          {roots.length === 0 ? (
            <p className="card-sub" style={{ margin: 0 }}>
              No standards tree. Import a standards workbook and run the pipeline.
            </p>
          ) : (
            roots.map((n) => <StandardTreeNode key={n.code} node={n} />)
          )}
        </div>
      </section>
    </div>
  )
}
