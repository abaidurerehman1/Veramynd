import { useEffect, useState } from 'react'

// Landing ticker: live figures from the most recent finished pipeline run, scrolling continuously.
type Metric = { label: string; value: string; note: string }

// Public summary of the latest finished run (counts only; see GET /api/public/latest-run).
type LatestRun = {
  available: boolean
  framework?: string
  grade?: number | string | null
  last_reviewed?: string | null
  lessons?: number
  standards?: number
  standards_leaves?: number
  alignments?: number
  full?: number
  partial?: number
  alignment_coverage_pct?: number
  positive_standards_cited?: number
  grounded?: number
  escalated?: number
  review_required?: number
  projects_aligned?: number
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

function toMetrics(r: LatestRun): Metric[] {
  // Uploads may have no framework/grade saved; fall back to plain labels instead of guessing.
  const fw = (r.framework || '').trim()
  const grade = r.grade != null && r.grade !== '' ? `Grade ${r.grade}` : ''
  const when = r.last_reviewed ? new Date(r.last_reviewed).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' }) : ''
  return [
    { label: 'Latest run', value: [fw, grade].filter(Boolean).join(' · ') || when || 'Complete', note: when ? `Finished ${when}` : 'Latest finished run' },
    { label: 'Lessons judged', value: n(r.lessons), note: 'Lessons in the teacher guide that were judged' },
    { label: fw ? `${fw} standards` : 'Framework standards', value: n(r.standards), note: 'Standards in the state framework' },
    { label: 'Alignments judged', value: n(r.alignments), note: 'Lesson × standard pairs the judge evaluated' },
    { label: 'Full matches', value: n(r.full), note: 'Every clause of the standard met' },
    { label: 'Partial matches', value: n(r.partial), note: 'Some clauses met' },
    { label: 'Coverage', value: typeof r.alignment_coverage_pct === 'number' ? `${r.alignment_coverage_pct}%` : '—', note: 'Share of leaf standards with at least one aligned lesson' },
    { label: 'Standards cited', value: `${n(r.positive_standards_cited)} of ${n(r.standards_leaves)}`, note: 'Leaf standards cited by at least one lesson' },
    { label: 'Evidence grounded', value: pct(r.grounded, r.alignments), note: 'Verdicts whose evidence was found on a page of the source' },
    { label: 'Escalated', value: n(r.escalated), note: 'Verdicts escalated to the stronger judge model' },
    { label: 'Awaiting SME review', value: n(r.review_required), note: 'Flagged citations waiting for an expert' },
    { label: 'Projects aligned', value: n(r.projects_aligned), note: 'Curriculum projects with finished results' },
  ]
}

/** Latest finished run from the public summary endpoint (no sign-in needed). */
async function loadLatestRun(): Promise<Metric[] | null> {
  const res = await fetch('/api/public/latest-run')
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  const r = (await res.json()) as LatestRun
  return r.available ? toMetrics(r) : null
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
