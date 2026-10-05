import { useMemo, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import type { ReviewItem } from '../api/types'
import {
  STATE_NAMES,
  cleanQuote,
  describeReviewReason,
  gradeLabel,
  gradesOf,
  lessonName,
  pageRange,
  rememberGrade,
  storedGrade,
  useAlignProjects,
  useReviewDecisions,
  useReviewQueue,
  type LeafStandard,
  type ProjectAlign,
} from '../components/align/data'
import { formatDecisionDate } from '../components/align/scale'
import { AlignTopbar, Kpi } from '../components/align/ui'
import { OverviewLoading } from '../components/OverviewStates'
import '../components/align/align.css'

type Filter = 'pending' | 'accepted' | 'rejected' | 'all'

// Confidence comes as a label; the bar shows it on a three-step scale, not a made-up percentage.
const CONFIDENCE: Record<string, { width: number; cls: string }> = {
  high: { width: 90, cls: 'hi' },
  medium: { width: 60, cls: 'mid' },
  low: { width: 30, cls: 'lo' },
}

type QueueItem = { it: ReviewItem; project: ProjectAlign; leaf?: LeafStandard }

/** SME review queue: flagged citations from every state project wait here until an expert accepts or rejects them. */
export function ReviewPage({ reloadKey = 0, projectId }: { reloadKey?: number; projectId: string }) {
  const navigate = useNavigate()
  const [params, setParams] = useSearchParams()
  const grade = params.get('grade') || storedGrade()
  const { data: alignProjects, error: alignError } = useAlignProjects(reloadKey)
  const projects = useMemo(() => alignProjects ?? [], [alignProjects])
  const ids = useMemo(() => projects.map((p) => p.project.id), [projects])
  const { rows: queue, error } = useReviewQueue(ids, reloadKey)
  const { decisions, available, error: decideError, decide } = useReviewDecisions(ids)
  const [filter, setFilter] = useState<Filter>('pending')
  const [busy, setBusy] = useState<string | null>(null)

  const items = useMemo(() => {
    const out: QueueItem[] = []
    projects
      .filter((p) => grade === 'all' || p.grade === grade)
      .forEach((p) => {
        const leafByCode = new Map(p.leaves.map((l) => [l.code, l]))
        ;(queue?.[p.project.id] ?? []).forEach((it) => out.push({ it, project: p, leaf: leafByCode.get(it.standard_code) }))
      })
    return out
  }, [projects, queue, grade])

  if (!alignProjects && !alignError) return <OverviewLoading />
  if (queue === null && ids.length) return <OverviewLoading />

  const decisionOf = (pid: string, id: string) => decisions[pid]?.[id]
  const statusOf = (pid: string, id: string): Exclude<Filter, 'all'> => decisionOf(pid, id)?.decision ?? 'pending'
  const counts = { pending: 0, accepted: 0, rejected: 0 }
  items.forEach(({ it, project }) => {
    counts[statusOf(project.project.id, it.id)] += 1
  })
  const shown = items.filter(({ it, project }) => filter === 'all' || statusOf(project.project.id, it.id) === filter)

  const act = async (pid: string, id: string, d: 'accepted' | 'rejected' | 'pending') => {
    setBusy(id)
    try {
      await decide(pid, id, d)
    } finally {
      setBusy(null)
    }
  }

  const setGrade = (g: string) => {
    rememberGrade(g)
    const next = new URLSearchParams(params)
    if (g === 'all') next.delete('grade')
    else next.set('grade', g)
    setParams(next)
  }

  return (
    <div className="va">
      <AlignTopbar
        trail={[{ label: 'National overview', onClick: () => navigate(`/projects/${projectId}/coverage`) }]}
        here="Expert review queue"
        grade={grade}
        gradeOptions={gradesOf(projects)}
        onGrade={setGrade}
        exportHref={`/projects/${projectId}/exports`}
      />
      <section className="va-screen">
        <div className="phead">
          <span className="eyebrow accent">The Veramynd method · Verify</span>
          <h1>
            Expert review queue<span className="bluedot">.</span>
          </h1>
          <p className="lede">
            Candidate alignments the judge flags are held here for a subject matter expert to confirm. Accept a citation
            to mark it verified, or reject it to return it for re-sourcing. Nothing counts as expert-verified until it is
            accepted, and every decision is saved with the reviewer’s name and date.
          </p>
        </div>

        <div className="kpis kpis-3">
          <Kpi label="Awaiting review" value={counts.pending} sub="Flagged for an expert" />
          <Kpi label="Accepted" value={counts.accepted} sub="Marked verified" accent />
          <Kpi label="Rejected" value={counts.rejected} sub="Returned for re-sourcing" />
        </div>

        {alignError ? <div className="va-error">Could not load projects: {alignError}</div> : null}
        {error ? <div className="va-error">Could not load the review queue: {error}</div> : null}
        {!available ? (
          <div className="va-error">Review storage is unavailable, so decisions can’t be saved right now.</div>
        ) : null}
        {decideError ? <div className="va-error">{decideError}</div> : null}

        <div className="panel">
          <div className="panel-head">
            <h2>Flagged citations</h2>
            <div className="filters" role="group" aria-label="Filter by decision">
              {(['pending', 'accepted', 'rejected', 'all'] as Filter[]).map((f) => (
                <button
                  key={f}
                  type="button"
                  className={`chip${filter === f ? ' on' : ''}`}
                  aria-pressed={filter === f}
                  onClick={() => setFilter(f)}
                >
                  {f[0].toUpperCase() + f.slice(1)}
                  <span className="chip-n">{f === 'all' ? items.length : counts[f]}</span>
                </button>
              ))}
            </div>
          </div>
          <div className="panel-body">
            <div className="rv-list">
              {shown.length === 0 ? <div className="rv-empty">Nothing in this view. The queue is clear.</div> : null}
              {shown.map(({ it, project, leaf }) => {
                const pid = project.project.id
                const status = statusOf(pid, it.id)
                const conf = CONFIDENCE[it.confidence] ?? CONFIDENCE.medium
                const decision = decisionOf(pid, it.id)
                const reason = describeReviewReason(it.review_reason)
                const matchCls = it.matched_status === 'full' ? 'met' : it.matched_status === 'partial' ? 'partial' : 'gap'
                const matchLabel = it.matched_status === 'full' ? 'Full' : it.matched_status === 'partial' ? 'Partial' : 'None'
                const frameworkLine = [
                  project.state ? STATE_NAMES[project.state] : project.project.name,
                  project.framework,
                  project.grade ? gradeLabel(project.grade) : null,
                ]
                  .filter(Boolean)
                  .join(' · ')
                const evidenceHref =
                  `/projects/${projectId}/coverage?` +
                  new URLSearchParams({
                    ...(project.state ? { state: project.state } : {}),
                    std: it.standard_code,
                    pid,
                    from: 'review',
                  }).toString()
                return (
                  <article className="rv-card" key={`${pid}:${it.id}`}>
                    <div className="rv-top">
                      <div>
                        <span className="rv-code">{it.standard_code}</span>
                        {leaf ? <span className="rv-strand">{leaf.domainLabel}</span> : null}
                        <div className="rv-state">{frameworkLine}</div>
                      </div>
                      <div className="rv-flag">
                        <span className={`badge fill ${matchCls}`}>
                          <span className="dot" />
                          {matchLabel} match
                        </span>
                        <div className="rv-reason">
                          {it.escalated ? 'Escalated · ' : ''}
                          {reason.headline}
                        </div>
                      </div>
                    </div>
                    {leaf ? <p className="rv-std">{leaf.text}</p> : <div style={{ height: 14 }} />}
                    {reason.note ? (
                      <p className="rv-note">
                        <span>Why it was flagged</span>
                        {reason.note}
                      </p>
                    ) : null}
                    <div className="rv-cite">
                      <div className="rv-cite-head">
                        <span className="rv-res">{lessonName(it.resource_id, it.lesson_title)}</span>
                        <span className="rv-loc">
                          {it.evidence_page ? pageRange([it.evidence_page]) : 'Teacher guide'}
                        </span>
                        <span className="rv-conf">
                          <span className="rv-conf-lbl">Model confidence</span>
                          <span className="rv-conf-bar" aria-hidden="true">
                            <span className={conf.cls} style={{ width: `${conf.width}%` }} />
                          </span>
                          <span className="rv-conf-num">{it.confidence || 'medium'}</span>
                        </span>
                      </div>
                      <div className="rv-ev">
                        {it.evidence ? <div className="ev-quote">“{cleanQuote(it.evidence)}”</div> : null}
                        {it.rationale}
                      </div>
                    </div>
                    <div className="rv-actions">
                      {status === 'pending' ? (
                        <>
                          <button
                            type="button"
                            className="btn primary"
                            disabled={busy === it.id || !available}
                            onClick={() => void act(pid, it.id, 'accepted')}
                          >
                            Accept citation
                          </button>
                          <button
                            type="button"
                            className="btn"
                            disabled={busy === it.id || !available}
                            onClick={() => void act(pid, it.id, 'rejected')}
                          >
                            Reject
                          </button>
                          <Link className="btn ghostlink" to={evidenceHref}>
                            Review full evidence →
                          </Link>
                        </>
                      ) : (
                        <>
                          <span className={`badge roll ${status === 'accepted' ? 'met' : 'gap'}`}>
                            <span className="dot" />
                            {status === 'accepted' ? 'Accepted' : 'Rejected'}
                          </span>
                          <span className="rv-done">
                            {status === 'accepted' ? 'Accepted, marked verified' : 'Rejected, returned for re-sourcing'}
                            {decision?.reviewer ? ` by ${decision.reviewer}` : ''}
                            {decision?.decided_at ? ` · ${formatDecisionDate(decision.decided_at)}` : ''}
                          </span>
                          <button
                            type="button"
                            className="btn ghostlink"
                            disabled={busy === it.id || !available}
                            onClick={() => void act(pid, it.id, 'pending')}
                          >
                            Undo
                          </button>
                        </>
                      )}
                    </div>
                  </article>
                )
              })}
            </div>
          </div>
        </div>
        <p className="screen-note">
          Alignments the judge marks low confidence, escalated or borderline are routed here. Accepted citations count as
          expert-verified on the National overview and on each standard’s evidence.
        </p>
      </section>
    </div>
  )
}

export default ReviewPage
