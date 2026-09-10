import { useCallback, useEffect, useRef, useState, type ChangeEvent, type FormEvent } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api/client'
import { ConfirmDialog } from '../components/ConfirmDialog'
import { IngestRunControls } from '../components/IngestRunControls'
import { OverviewLoading } from '../components/OverviewStates'
import type { RunnableStep } from '../components/PipelineRunPanel'
import { NONE_PROJECT_ID, useProject } from '../project/ProjectContext'

type IngestBatch = { id: string; name?: string; files: string[] }

type IngestStatus = {
  uploads_dir?: string
  note?: string
  batches: IngestBatch[]
  runnable_steps?: RunnableStep[]
}

function detailMessage(body: { detail?: unknown; message?: string }, status: number): string {
  const detail = body?.detail
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) {
    return detail.map((d: { msg?: string }) => d.msg || JSON.stringify(d)).join('; ')
  }
  return body?.message || `HTTP ${status}`
}

function formatBytes(n: number) {
  if (n < 1024) return `${n} B`
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`
  return `${(n / (1024 * 1024)).toFixed(1)} MB`
}

function FileDropField({
  name,
  label,
  hint,
  accept,
  file,
  onFile,
  icon,
}: {
  name: string
  label: string
  hint: string
  accept: string
  file: File | null
  onFile: (f: File | null) => void
  icon: 'pdf' | 'xlsx'
}) {
  const inputRef = useRef<HTMLInputElement>(null)
  const [dragOver, setDragOver] = useState(false)

  const pick = (list: FileList | null) => {
    const f = list?.[0] || null
    onFile(f)
  }

  return (
    <div className={`ingest-drop ${dragOver ? 'drag' : ''} ${file ? 'has-file' : ''}`}>
      <input
        ref={inputRef}
        name={name}
        type="file"
        accept={accept}
        className="ingest-drop-input"
        onChange={(e: ChangeEvent<HTMLInputElement>) => pick(e.target.files)}
      />
      <button
        type="button"
        className="ingest-drop-hit"
        onClick={() => inputRef.current?.click()}
        onDragEnter={(e) => {
          e.preventDefault()
          setDragOver(true)
        }}
        onDragOver={(e) => {
          e.preventDefault()
          setDragOver(true)
        }}
        onDragLeave={() => setDragOver(false)}
        onDrop={(e) => {
          e.preventDefault()
          setDragOver(false)
          pick(e.dataTransfer.files)
        }}
      >
        <span className={`ingest-drop-icon ${icon}`} aria-hidden>
          {icon === 'pdf' ? (
            <svg width="22" height="22" viewBox="0 0 24 24" fill="none">
              <path
                d="M8 3.5h5.2L17.5 7.8V19a1.5 1.5 0 0 1-1.5 1.5H8A1.5 1.5 0 0 1 6.5 19V5A1.5 1.5 0 0 1 8 3.5Z"
                stroke="currentColor"
                strokeWidth="1.5"
              />
              <path d="M13.2 3.5V7.8H17.5" stroke="currentColor" strokeWidth="1.5" />
              <path d="M9 12.5h6M9 15.5h4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
            </svg>
          ) : (
            <svg width="22" height="22" viewBox="0 0 24 24" fill="none">
              <rect x="4.5" y="5" width="15" height="14" rx="2" stroke="currentColor" strokeWidth="1.5" />
              <path d="M4.5 9.5h15M10 9.5v9.5" stroke="currentColor" strokeWidth="1.5" />
            </svg>
          )}
        </span>
        <span className="ingest-drop-copy">
          <strong>{label}</strong>
          {file ? (
            <span className="ingest-drop-file">
              {file.name}
              <em>{formatBytes(file.size)}</em>
            </span>
          ) : (
            <span>{hint}</span>
          )}
        </span>
        <span className="ingest-drop-cta">{file ? 'Replace' : 'Browse'}</span>
      </button>
      {file ? (
        <button
          type="button"
          className="ingest-drop-clear"
          aria-label={`Clear ${label}`}
          title="Clear"
          onClick={(e) => {
            e.stopPropagation()
            onFile(null)
            if (inputRef.current) inputRef.current.value = ''
          }}
        >
          <svg width="12" height="12" viewBox="0 0 12 12" aria-hidden>
            <path
              d="M3 3l6 6M9 3L3 9"
              stroke="currentColor"
              strokeWidth="1.7"
              strokeLinecap="round"
            />
          </svg>
        </button>
      ) : null}
    </div>
  )
}

export function IngestionPage({ reloadKey = 0 }: { reloadKey?: number }) {
  const { projectId, hasProject, project, refreshProjects, setProjectId } = useProject()
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [deletingId, setDeletingId] = useState<string | null>(null)
  const [deleteTarget, setDeleteTarget] = useState<IngestBatch | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [msg, setMsg] = useState<string | null>(null)
  const [lastProjectId, setLastProjectId] = useState<string | null>(null)
  const [status, setStatus] = useState<IngestStatus>({ batches: [] })
  const [activeBatchId, setActiveBatchId] = useState<string | null>(null)
  const [pdfFile, setPdfFile] = useState<File | null>(null)
  const [xlsxFile, setXlsxFile] = useState<File | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const data = await api<IngestStatus>('/api/ingest')
      const batches = data.batches || []
      setStatus({
        uploads_dir: data.uploads_dir,
        note: data.note,
        batches,
        runnable_steps: data.runnable_steps,
      })
      setActiveBatchId((prev) => {
        if (prev && batches.some((b) => b.id === prev)) return prev
        return batches[0]?.id ?? null
      })
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
      setStatus({ batches: [] })
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load, reloadKey])

  const onSubmit = async (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault()
    setMsg(null)
    setError(null)
    const form = e.currentTarget
    const fd = new FormData(form)
    // Ensure controlled file picks are in FormData
    if (pdfFile) fd.set('guide_pdf', pdfFile)
    else fd.delete('guide_pdf')
    if (xlsxFile) fd.set('standards_xlsx', xlsxFile)
    else fd.delete('standards_xlsx')

    if (!pdfFile || !xlsxFile) {
      setError('Both a curriculum PDF and a standards XLSX are required.')
      return
    }
    setSaving(true)
    try {
      const res = await fetch('/api/ingest', { method: 'POST', body: fd })
      const body = await res.json().catch(() => ({}))
      if (!res.ok) throw new Error(detailMessage(body, res.status))
      const batchId = body.batch_id as string | undefined
      const uploadProjectId =
        (body.project_id as string | undefined) || (batchId ? `upload-${batchId}` : null)
      setMsg(
        body.message ||
          `Saved batch ${batchId || '—'}. Run explicitly below — nothing starts on save.`,
      )
      form.reset()
      setPdfFile(null)
      setXlsxFile(null)
      await load()
      await refreshProjects()
      if (batchId) setActiveBatchId(batchId)
      if (uploadProjectId) setLastProjectId(uploadProjectId)
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setSaving(false)
    }
  }

  const confirmDelete = async () => {
    if (!deleteTarget) return
    const id = deleteTarget.id
    setDeletingId(id)
    setError(null)
    try {
      const res = await fetch(`/api/ingest/${encodeURIComponent(id)}`, { method: 'DELETE' })
      const body = await res.json().catch(() => ({}))
      if (!res.ok) throw new Error(detailMessage(body, res.status))
      setMsg(`Deleted batch ${id}.`)
      setDeleteTarget(null)
      if (lastProjectId === `upload-${id}`) setLastProjectId(null)
      await load()
      await refreshProjects()
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
      setDeleteTarget(null)
    } finally {
      setDeletingId(null)
    }
  }

  if (loading) return <OverviewLoading />

  const batches = status.batches
  const activeUploadProjectId = activeBatchId ? `upload-${activeBatchId}` : lastProjectId
  const pipelineTo = activeUploadProjectId
    ? `/projects/${activeUploadProjectId}/pipeline`
    : hasProject
      ? `/projects/${projectId}/pipeline`
      : `/projects/${NONE_PROJECT_ID}/pipeline`
  const logsPath = hasProject
    ? `/projects/${projectId}/logging`
    : activeUploadProjectId
      ? `/projects/${activeUploadProjectId}/logging`
      : `/projects/${NONE_PROJECT_ID}/logging`
  const steps = status.runnable_steps || []
  const readyToSave = Boolean(pdfFile && xlsxFile)
  const activeBatch = batches.find((b) => b.id === activeBatchId) || null
  const activeBatchName = activeBatch?.name || activeBatchId || null

  return (
    <div className="analytics">
      <div className="page-header">
        <h1>Ingestion</h1>
        <p>
          Add curriculum and standards inputs, then run explicitly
          {hasProject && project ? ` · viewing ${project.name}` : ''}.
        </p>
      </div>

      <div className="kpi-grid kpi-4">
        <div className="kpi">
          <div className="label">Upload batches</div>
          <div className="value">{batches.length}</div>
        </div>
        <div className="kpi">
          <div className="label">Active batch</div>
          <div className="value kpi-batch-name" title={activeBatchId || undefined}>
            {activeBatchName || '—'}
          </div>
        </div>
        <div className="kpi">
          <div className="label">Run modes</div>
          <div className="value" style={{ fontSize: 18 }}>
            Auto / steps
          </div>
        </div>
        <div className="kpi">
          <div className="label">Auto-run on upload</div>
          <div className="value" style={{ fontSize: 18 }}>
            Never
          </div>
        </div>
      </div>

      <section className="card ingest-hero-card">
        <div className="ingest-hero">
          <div className="ingest-hero-main">
            <div className="ingest-hero-kicker">New project inputs</div>
            <h2>Upload curriculum + standards</h2>
            <p>
              Files are stored locally as a batch. The pipeline never starts until you confirm a run.
            </p>

            <form
              className="ingest-form ingest-form-pro"
              onSubmit={(e) => void onSubmit(e)}
            >
              <div className="ingest-meta-block">
                <div className="ingest-section-label">Project details</div>

                <label>
                  Title / program
                  <input
                    name="program_name"
                    type="text"
                    defaultValue=""
                    placeholder="School, publisher, or project title"
                  />
                </label>
                <div className="ingest-row">
                  <label>
                    Unit / scope
                    <input
                      name="guide_label"
                      type="text"
                      defaultValue=""
                      placeholder="Module, unit, course, etc."
                    />
                  </label>
                  <label>
                    Level / grade
                    <input
                      name="grade_label"
                      type="text"
                      defaultValue=""
                      placeholder="Grade, band, or level"
                    />
                  </label>
                </div>
              </div>

              <div className="ingest-files-block">
                <div className="ingest-section-label">Source files</div>
                <div className="ingest-drop-grid">
                  <FileDropField
                    name="guide_pdf"
                    label="Curriculum PDF"
                    hint="Required · drag & drop or browse · PDF"
                    accept=".pdf,application/pdf"
                    file={pdfFile}
                    onFile={setPdfFile}
                    icon="pdf"
                  />
                  <FileDropField
                    name="standards_xlsx"
                    label="Standards workbook"
                    hint="Required · drag & drop or browse · XLSX / XLSM"
                    accept=".xlsx,.xlsm"
                    file={xlsxFile}
                    onFile={setXlsxFile}
                    icon="xlsx"
                  />
                </div>
              </div>

              <div className="ingest-actions-pro">
                <button type="submit" className="btn primary" disabled={saving || !readyToSave}>
                  {saving ? 'Saving…' : 'Save inputs'}
                </button>
                <Link className="btn" to={pipelineTo}>
                  Pipeline
                </Link>
                {activeUploadProjectId ? (
                  <button
                    type="button"
                    className="btn outline-green"
                    onClick={() => setProjectId(activeUploadProjectId)}
                  >
                    Open Overview
                  </button>
                ) : null}
                <span className="ingest-actions-hint">
                  {readyToSave
                    ? 'Ready to save · no auto-run'
                    : 'Add curriculum PDF and standards XLSX to continue'}
                </span>
              </div>

              {error ? <p className="none-error">{error}</p> : null}
              {msg ? <p className="none-ok">{msg}</p> : null}
            </form>
          </div>

          <aside className="ingest-hero-aside">
            <div className="ingest-aside-title">Process</div>
            <ol className="ingest-aside-steps">
              <li>
                <span>01</span>
                <div>
                  <strong>Save inputs</strong>
                  <p>PDF + standards stored as a batch</p>
                </div>
              </li>
              <li>
                <span>02</span>
                <div>
                  <strong>Confirm a run</strong>
                  <p>Complete auto or step by step</p>
                </div>
              </li>
              <li>
                <span>03</span>
                <div>
                  <strong>Review results</strong>
                  <p>Overview fills when output is ready</p>
                </div>
              </li>
            </ol>

          </aside>
        </div>
      </section>

      <section className="card">
        <div className="card-h">
          <h2>Run against upload batch</h2>
          {activeBatchId ? (
            <span className="badge info">{activeBatchName || activeBatchId}</span>
          ) : null}
        </div>
        <div className="card-b">
          {batches.length === 0 ? (
            <p className="card-sub" style={{ margin: 0 }}>
              Save a PDF + XLSX first. Nothing runs until you explicitly start a job below.
            </p>
          ) : (
            <>
              <label className="ingest-batch-pick">
                Batch
                <select
                  value={activeBatchId || ''}
                  onChange={(e) => setActiveBatchId(e.target.value || null)}
                >
                  {batches.map((b) => (
                    <option key={b.id} value={b.id}>
                      {b.name || b.id}
                    </option>
                  ))}
                </select>
              </label>
              {activeBatchId ? (
                <IngestRunControls batchId={activeBatchId} steps={steps} logsPath={logsPath} />
              ) : null}
            </>
          )}
        </div>
      </section>

      <section className="card">
        <div className="card-h">
          <h2>Recent uploads</h2>
          <span className="badge info">{batches.length}</span>
        </div>
        <div className="card-b">
          {batches.length === 0 ? (
            <div className="ingest-empty-batches">
              <strong>No uploads yet</strong>
              <p>Add a curriculum PDF and standards workbook above to create your first batch.</p>
            </div>
          ) : (
            <div className="batch-grid">
              {batches.map((b) => {
                const files = (b.files || []).filter((f) => f !== 'meta.json')
                return (
                  <article
                    className={`batch-card ${activeBatchId === b.id ? 'selected' : ''}`}
                    key={b.id}
                  >
                    <button
                      type="button"
                      className="batch-card-main"
                      onClick={() => setActiveBatchId(b.id)}
                    >
                      <div className="batch-card-kicker">
                        {activeBatchId === b.id ? 'Active batch' : 'Upload batch'}
                      </div>
                      <div className="batch-id">{b.name || b.id}</div>
                      {b.name && b.name !== b.id ? (
                        <div className="batch-id-sub">{b.id}</div>
                      ) : null}
                      <div className="batch-files">
                        {files.length ? (
                          files.map((f) => (
                            <span className="batch-file-chip" key={f}>
                              {f}
                            </span>
                          ))
                        ) : (
                          <span className="card-sub">No files</span>
                        )}
                      </div>
                    </button>
                    <div className="batch-card-actions">
                      <button type="button" className="btn" onClick={() => setActiveBatchId(b.id)}>
                        Use
                      </button>
                      <button
                        type="button"
                        className="btn outline-green"
                        onClick={() => setProjectId(`upload-${b.id}`)}
                      >
                        Overview
                      </button>
                      <button
                        type="button"
                        className="btn danger-ghost"
                        disabled={deletingId === b.id}
                        onClick={() => setDeleteTarget(b)}
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
        title="Delete upload batch?"
        body={
          deleteTarget
            ? `Permanently delete batch ${deleteTarget.id} and any pipeline output under it? Job logs stay on Logging until you Clear logs.`
            : ''
        }
        confirmLabel="Delete batch"
        danger
        busy={Boolean(deletingId)}
        onCancel={() => !deletingId && setDeleteTarget(null)}
        onConfirm={() => void confirmDelete()}
      />
    </div>
  )
}
