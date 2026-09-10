import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api/client'
import { ConfirmDialog } from '../components/ConfirmDialog'
import type { PipelineJob } from '../components/LivePipelineProgress'
import { OverviewLoading } from '../components/OverviewStates'
import { useProject } from '../project/ProjectContext'

type LogEntry = {
  job_id: string
  line_no: number
  type: string
  type_label: string
  message: string
  job_status?: string
  mode?: string
  project_id?: string | null
  batch_id?: string | null
  created_at?: string
  stage_id?: string | null
  stage_name?: string | null
  lesson_code?: string | null
  lesson_index?: number | null
  lesson_total?: number | null
  action?: string | null
}

type StageLesson = {
  code: string
  action?: string | null
  index?: number | null
  total?: number | null
  status: string
  message: string
  line_no: number
}

type StageBlock = {
  job_id: string
  stage_id: string
  stage_name: string
  status: string
  lessons: StageLesson[]
  lesson_count: number
  ok: number
  skip: number
  error: number
  running: number
  cost_usd?: number | null
}

type JobCost = {
  job_id: string
  total_cost_usd: number
  stage_costs?: Record<string, number>
  status?: string
  mode?: string
}

type LogsResponse = {
  jobs: PipelineJob[]
  entries: LogEntry[]
  stages?: StageBlock[]
  job_costs?: JobCost[]
  total_cost_usd?: number
  by_type: Record<string, LogEntry[]>
  counts: Record<string, number>
  type_labels: Record<string, string>
}

function formatUsd(n: number | null | undefined) {
  if (n == null || Number.isNaN(n)) return '—'
  if (n === 0) return '$0.00'
  if (n < 0.01) return `$${n.toFixed(4)}`
  return `$${n.toFixed(2)}`
}

function typeBadge(t: string) {
  if (t === 'warning' || t === 'info' || t === 'stage' || t === 'lesson' || t === 'cost') return 'info'
  if (t === 'validation') return 'neutral'
  return 'warn'
}

function lessonBadge(status: string) {
  if (status === 'error') return 'warn'
  if (status === 'done' || status === 'ok') return 'ok'
  if (status === 'skip') return 'neutral'
  return 'info'
}

export function LoggingPage({ reloadKey = 0 }: { reloadKey?: number }) {
  const { projectId, hasProject } = useProject()
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [data, setData] = useState<LogsResponse | null>(null)
  const [filterType, setFilterType] = useState<string>('all')
  const [selectedJobId, setSelectedJobId] = useState<string>('')
  const [expandedStage, setExpandedStage] = useState<string | null>(null)
  const [rawLog, setRawLog] = useState('')
  const [confirmClear, setConfirmClear] = useState(false)
  const [clearing, setClearing] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const q = selectedJobId ? `?job_id=${encodeURIComponent(selectedJobId)}&limit=40` : '?limit=40'
      const res = await api<LogsResponse>(`/api/pipeline/logs${q}`)
      setData(res)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
      setData(null)
    } finally {
      setLoading(false)
    }
  }, [selectedJobId])

  const clearLogs = async () => {
    setClearing(true)
    setError(null)
    try {
      const res = await fetch('/api/pipeline/logs', { method: 'DELETE' })
      if (!res.ok) throw new Error((await res.text()) || `HTTP ${res.status}`)
      setConfirmClear(false)
      setSelectedJobId('')
      setRawLog('')
      setExpandedStage(null)
      await load()
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setClearing(false)
    }
  }

  useEffect(() => {
    void load()
  }, [load, reloadKey])

  useEffect(() => {
    if (!selectedJobId) {
      setRawLog('')
      return
    }
    void api<{ log?: string }>(`/api/pipeline/jobs/${selectedJobId}?log=true`)
      .then((d) => setRawLog(d.log || ''))
      .catch(() => setRawLog(''))
  }, [selectedJobId, reloadKey])

  useEffect(() => {
    const live = data?.jobs?.some((j) => j.status === 'running' || j.status === 'queued')
    if (!live) return
    const t = window.setInterval(() => {
      void load()
    }, 2500)
    return () => window.clearInterval(t)
  }, [data?.jobs, load])

  const stages = useMemo(() => {
    let rows = data?.stages || []
    if (selectedJobId) rows = rows.filter((s) => s.job_id === selectedJobId)
    return rows
  }, [data, selectedJobId])

  const lessonTotal = useMemo(
    () => stages.reduce((n, s) => n + (s.lesson_count || 0), 0),
    [stages],
  )

  const costSummary = useMemo(() => {
    const rows = data?.job_costs || []
    const selected = selectedJobId ? rows.find((r) => r.job_id === selectedJobId) : null
    const total =
      selected != null
        ? selected.total_cost_usd
        : typeof data?.total_cost_usd === 'number'
          ? data.total_cost_usd
          : rows.reduce((n, r) => n + (r.total_cost_usd || 0), 0)
    return { selected, total, rows }
  }, [data, selectedJobId])

  const entries = useMemo(() => {
    let rows = data?.entries || []
    if (filterType !== 'all') rows = rows.filter((e) => e.type === filterType)
    return rows
  }, [data, filterType])

  const base = hasProject ? `/projects/${projectId}` : `/projects/none`

  if (loading && !data) return <OverviewLoading />

  return (
    <div className="analytics">
      <div className="page-header">
        <div>
          <h1>Logging</h1>
          <p>Per-stage and per-lesson pipeline activity, plus typed errors.</p>
        </div>
        <div className="header-actions">
          <button
            type="button"
            className="btn danger-ghost"
            disabled={clearing || !(data?.jobs?.length || data?.entries?.length)}
            onClick={() => setConfirmClear(true)}
          >
            Clear logs
          </button>
        </div>
      </div>

      <div className="kpi-grid kpi-4">
        <div className="kpi">
          <div className="label">Jobs</div>
          <div className="value">{data?.jobs?.length ?? 0}</div>
        </div>
        <div className="kpi">
          <div className="label">Stages</div>
          <div className="value">{stages.length}</div>
        </div>
        <div className="kpi">
          <div className="label">Lesson events</div>
          <div className="value">{lessonTotal}</div>
        </div>
        <div className="kpi">
          <div className="label">Typed lines</div>
          <div className="value">{data?.entries?.length ?? 0}</div>
        </div>
      </div>

      {error ? (
        <div className="error-box">
          <h3>Unable to load logs</h3>
          <p>{error}</p>
          <button type="button" className="btn" onClick={() => void load()}>
            Retry
          </button>
        </div>
      ) : null}

      <section className="card">
        <div className="card-h">
          <h2>Stages & lessons</h2>
          <div className="log-actions">
            <button type="button" className="btn" onClick={() => void load()}>
              Refresh
            </button>
            <Link className="btn" to={`${base}/pipeline`}>
              Pipeline
            </Link>
          </div>
        </div>
        <div className="card-b">
          <div className="log-cost-banner" style={{ marginBottom: 12 }}>
            <span className="badge info">
              {selectedJobId ? 'Job cost' : 'All jobs cost'} · {formatUsd(costSummary.total)}
            </span>
            {costSummary.selected?.stage_costs &&
            Object.keys(costSummary.selected.stage_costs).length ? (
              <span className="card-sub" style={{ marginLeft: 8 }}>
                {Object.entries(costSummary.selected.stage_costs)
                  .map(([k, v]) => `${k} ${formatUsd(v)}`)
                  .join(' · ')}
              </span>
            ) : (
              <span className="card-sub" style={{ marginLeft: 8 }}>
                Per-stage costs appear after Normalize / Embed / Judge emit usage lines.
              </span>
            )}
          </div>
          {stages.length === 0 ? (
            <p className="card-sub" style={{ margin: 0 }}>
              No stage/lesson activity yet. Run a pipeline job — normalize, retrieve, and judge
              lines appear here per lesson.
            </p>
          ) : (
            <div className="log-stage-list">
              {stages.map((s) => {
                const key = `${s.job_id}:${s.stage_id}:${s.stage_name}`
                const open = expandedStage === key || (expandedStage === null && s.lesson_count > 0 && s === stages[0])
                return (
                  <article className={`log-stage-card ${s.status}`} key={key}>
                    <button
                      type="button"
                      className="log-stage-head"
                      onClick={() => setExpandedStage(open ? '' : key)}
                    >
                      <div>
                        <strong>{s.stage_name || s.stage_id}</strong>
                        <span className="card-sub">
                          {s.job_id} · {s.lesson_count} lessons
                          {s.ok ? ` · ${s.ok} ok` : ''}
                          {s.skip ? ` · ${s.skip} skip` : ''}
                          {s.error ? ` · ${s.error} error` : ''}
                          {s.running ? ` · ${s.running} running` : ''}
                          {s.cost_usd != null ? ` · ${formatUsd(s.cost_usd)}` : ''}
                        </span>
                      </div>
                      <span className={`badge ${s.status === 'complete' ? 'ok' : s.status === 'failed' ? 'warn' : 'info'}`}>
                        {s.cost_usd != null ? `${s.status} · ${formatUsd(s.cost_usd)}` : s.status}
                      </span>
                    </button>
                    {open ? (
                      <div className="log-lesson-table">
                        {s.lessons.length === 0 ? (
                          <p className="card-sub" style={{ margin: 0 }}>
                            Stage marker only — no per-lesson lines captured for this stage yet.
                          </p>
                        ) : (
                          s.lessons
                            .slice()
                            .sort((a, b) => (a.index || 0) - (b.index || 0) || a.code.localeCompare(b.code))
                            .map((L) => (
                              <div className={`log-lesson-row status-${L.status}`} key={`${L.code}-${L.line_no}`}>
                                <code className="log-lesson-code">{L.code}</code>
                                <span className="card-sub">
                                  {L.index != null && L.total != null ? `${L.index}/${L.total}` : '—'}
                                  {L.action ? ` · ${L.action}` : ''}
                                </span>
                                <span className={`badge ${lessonBadge(L.status)}`}>{L.status}</span>
                                <span className="log-lesson-msg" title={L.message}>
                                  {L.message}
                                </span>
                              </div>
                            ))
                        )}
                      </div>
                    ) : null}
                  </article>
                )
              })}
            </div>
          )}
        </div>
      </section>

      <section className="card">
        <div className="card-h">
          <h2>Filter by type</h2>
        </div>
        <div className="card-b">
          <div className="log-type-chips">
            <button
              type="button"
              className={`log-chip ${filterType === 'all' ? 'active' : ''}`}
              onClick={() => setFilterType('all')}
            >
              All <span>{data?.entries?.length ?? 0}</span>
            </button>
            {Object.entries(data?.counts || {}).map(([tid, n]) => (
              <button
                key={tid}
                type="button"
                className={`log-chip ${filterType === tid ? 'active' : ''} ${tid}`}
                onClick={() => setFilterType(tid)}
              >
                {data?.type_labels?.[tid] || tid} <span>{n}</span>
              </button>
            ))}
          </div>
        </div>
      </section>

      <div className="grid-2">
        <section className="card">
          <div className="card-h">
            <h2>Jobs</h2>
          </div>
          <div className="card-b">
            {(data?.jobs || []).length === 0 ? (
              <p className="card-sub" style={{ margin: 0 }}>
                No pipeline jobs yet.
              </p>
            ) : (
              <div className="log-job-list">
                <button
                  type="button"
                  className={`log-job-row ${!selectedJobId ? 'selected' : ''}`}
                  onClick={() => setSelectedJobId('')}
                >
                  <strong>All jobs</strong>
                  <span className="card-sub">
                    combined stage / lesson view · {formatUsd(data?.total_cost_usd)}
                  </span>
                </button>
                {(data?.jobs || []).map((j) => {
                  const jc = (data?.job_costs || []).find((c) => c.job_id === j.id)
                  const cost =
                    jc?.total_cost_usd ??
                    (typeof (j as PipelineJob & { total_cost_usd?: number }).total_cost_usd ===
                    'number'
                      ? (j as PipelineJob & { total_cost_usd?: number }).total_cost_usd
                      : undefined)
                  return (
                  <button
                    key={j.id}
                    type="button"
                    className={`log-job-row ${selectedJobId === j.id ? 'selected' : ''}`}
                    onClick={() => setSelectedJobId(j.id)}
                  >
                    <div className="log-job-top">
                      <code>{j.id}</code>
                      <span
                        className={`badge ${j.status === 'succeeded' ? 'ok' : j.status === 'failed' ? 'warn' : 'info'}`}
                      >
                        {j.status}
                        {typeof j.percent === 'number' ? ` · ${j.percent}%` : ''}
                        {cost != null ? ` · ${formatUsd(cost)}` : ''}
                      </span>
                    </div>
                    <span className="card-sub">
                      {j.mode}
                      {j.project_id ? ` · ${j.project_id}` : ''}
                      {j.batch_id ? ` · batch ${j.batch_id}` : ''}
                    </span>
                  </button>
                  )
                })}
              </div>
            )}
          </div>
        </section>

        <section className="card">
          <div className="card-h">
            <h2>Typed entries</h2>
            <span className="badge info">{entries.length}</span>
          </div>
          <div className="card-b">
            {entries.length === 0 ? (
              <p className="card-sub" style={{ margin: 0 }}>
                No entries for this filter.
              </p>
            ) : (
              <div className="log-entry-list">
                {entries.slice(0, 300).map((e, idx) => (
                  <article className={`log-entry type-${e.type}`} key={`${e.job_id}-${e.line_no}-${idx}`}>
                    <div className="log-entry-top">
                      <span className={`badge ${typeBadge(e.type)}`}>{e.type_label}</span>
                      {e.stage_name ? <span className="badge neutral">{e.stage_name}</span> : null}
                      {e.lesson_code ? <code className="log-entry-job">{e.lesson_code}</code> : null}
                      <code className="log-entry-job">{e.job_id}</code>
                      <span className="card-sub">L{e.line_no}</span>
                    </div>
                    <pre className="log-entry-msg">{e.message}</pre>
                  </article>
                ))}
              </div>
            )}
          </div>
        </section>
      </div>

      {selectedJobId ? (
        <section className="card">
          <div className="card-h">
            <h2>Full log · {selectedJobId}</h2>
          </div>
          <div className="card-b">
            {rawLog ? (
              <pre className="pipe-log" tabIndex={0}>
                {rawLog}
              </pre>
            ) : (
              <p className="card-sub" style={{ margin: 0 }}>
                No log file for this job.
              </p>
            )}
          </div>
        </section>
      ) : null}

      <ConfirmDialog
        open={confirmClear}
        title="Clear all logs?"
        body="Permanently delete all pipeline job records and log files from this dashboard. This cannot be undone."
        confirmLabel="Clear logs"
        danger
        busy={clearing}
        onCancel={() => !clearing && setConfirmClear(false)}
        onConfirm={() => void clearLogs()}
      />
    </div>
  )
}
