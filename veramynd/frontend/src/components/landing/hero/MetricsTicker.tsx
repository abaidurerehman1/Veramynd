import { useEffect, useState } from 'react'

// Landing ticker: live figures from the most recent finished pipeline run, scrolling continuously.
type Metric = { label: string; value: string; note: string }

type ProjectRow = {
  id: string
  name?: string
  framework?: string
  grade?: number | string | null
  has_output?: boolean
  run_status?: string
}

type Overview = {
  readiness?: string
  last_reviewed?: string | null
  lessons?: number
  standards?: number
  standards_leaves?: number
  alignments?: number
  review_required?: number
  escalated?: number
  alignment_coverage_pct?: number
  grounded?: number
  positive_standards_cited?: number
  by_status?: { full?: number; partial?: number; none?: number }
}

// Shown only if the live figures cannot be loaded (Batch-1 gold-set results).
const FALLBACK: Metric[] = [
  { label: 'Recall@25', value: '100%', note: 'Retrieval recall on 20 SME-labeled positives' },
  { label: 'Judge exact', value: '20/20', note: '3-class match vs SME on four gold lessons' },
  { label: 'vs SME master', value: '93.1%', note: '95 of 102 pairs on the four-lesson overlap' },
  { label: 'Lessons judged', value: '40', note: 'Every lesson in the Batch-1 teacher guide' },
  { label: 'GA ELA standards', value: '188', note: 'Georgia Grade 1 ELA framework, adopted 2023' },
  { label: 'Binary precision', value: '100%', note: 'Full-or-partial vs none, on the four gold lessons' },
]

const n = (v?: number | null) => (typeof v === 'number' ? v.toLocaleString() : '—')
const pct = (part?: number, whole?: number) =>
  typeof part === 'number' && whole ? `${Math.round((100 * part) / whole)}%` : '—'

function toMetrics(project: ProjectRow, ov: Overview, readyCount: number): Metric[] {
  // Uploads may have no framework/grade saved; fall back to plain labels instead of guessing.
  const fw = (project.framework || '').trim()
  const grade = project.grade != null && project.grade !== '' ? `Grade ${project.grade}` : ''
  const full = ov.by_status?.full
  const partial = ov.by_status?.partial
  const when = ov.last_reviewed ? new Date(ov.last_reviewed).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' }) : ''
  return [
    {
      label: 'Latest run',
      value: [fw, grade].filter(Boolean).join(' · ') || when || 'Complete',
      note: `${project.name || project.id}${when ? ` · ${when}` : ''}`,
    },
    { label: 'Lessons judged', value: n(ov.lessons), note: 'Lessons in the teacher guide that were judged' },
    { label: fw ? `${fw} standards` : 'Framework standards', value: n(ov.standards), note: 'Standards in the state framework' },
    { label: 'Alignments judged', value: n(ov.alignments), note: 'Lesson × standard pairs the judge evaluated' },
    { label: 'Full matches', value: n(full), note: 'Every clause of the standard met' },
    { label: 'Partial matches', value: n(partial), note: 'Some clauses met' },
    { label: 'Coverage', value: typeof ov.alignment_coverage_pct === 'number' ? `${ov.alignment_coverage_pct}%` : '—', note: 'Share of leaf standards with at least one aligned lesson' },
    { label: 'Standards cited', value: `${n(ov.positive_standards_cited)} of ${n(ov.standards_leaves)}`, note: 'Leaf standards cited by at least one lesson' },
    { label: 'Evidence grounded', value: pct(ov.grounded, ov.alignments), note: 'Verdicts whose evidence was found on a page of the source' },
    { label: 'Escalated', value: n(ov.escalated), note: 'Verdicts escalated to the stronger judge model' },
    { label: 'Awaiting SME review', value: n(ov.review_required), note: 'Flagged citations waiting for an expert' },
    { label: 'Projects aligned', value: n(readyCount), note: 'Curriculum projects with finished results' },
  ]
}

async function getJson<T>(url: string): Promise<T> {
  const res = await fetch(url, { credentials: 'include' })
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  return (await res.json()) as T
}

/** Most recent project whose pipeline finished with alignments, plus how many are finished. */
async function loadLatestRun(): Promise<Metric[] | null> {
  const { projects } = await getJson<{ projects: ProjectRow[] }>('/api/projects')
  const candidates = projects.filter((p) => p.has_output && p.run_status === 'ready')
  const overviews = await Promise.all(
    candidates.map((p) =>
      getJson<Overview>(`/api/overview?project_id=${encodeURIComponent(p.id)}`)
        .then((ov) => ({ p, ov }))
        .catch(() => null),
    ),
  )
  const finished = overviews.filter(
    (x): x is { p: ProjectRow; ov: Overview } => !!x && x.ov.readiness === 'ready' && (x.ov.alignments ?? 0) > 0,
  )
  if (!finished.length) return null
  finished.sort((a, b) => Date.parse(b.ov.last_reviewed || '') - Date.parse(a.ov.last_reviewed || ''))
  return toMetrics(finished[0].p, finished[0].ov, finished.length)
}

export function MetricsTicker() {
  const [metrics, setMetrics] = useState<Metric[]>(FALLBACK)
  const [live, setLive] = useState(false)

  useEffect(() => {
    let cancelled = false
    loadLatestRun()
      .then((m) => {
        if (!cancelled && m) {
          setMetrics(m)
          setLive(true)
        }
      })
      .catch(() => undefined)
    return () => {
      cancelled = true
    }
  }, [])

  // The list is rendered twice so the scroll loops seamlessly; the copy is hidden from screen readers.
  const items = (copy: boolean) =>
    metrics.map((m) => (
      <li className="fs-ticker__item" key={`${copy ? 'b' : 'a'}-${m.label}`} title={m.note} aria-hidden={copy || undefined}>
        <span>{m.label}</span>
        <span>
          <span aria-hidden="true">↗</span> {m.value}
        </span>
      </li>
    ))

  return (
    <div className="fs-ticker" role="region" aria-label={live ? 'Latest pipeline results' : 'Gold-set results'}>
      <div className="fs-ticker__track">
        <ul className="fs-ticker__list">{items(false)}</ul>
        <ul className="fs-ticker__list" aria-hidden="true">
          {items(true)}
        </ul>
      </div>
    </div>
  )
}

export default MetricsTicker
