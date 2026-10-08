import { useMemo, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import type { AlignmentRow } from '../api/types'
import {
  STATE_NAMES,
  gradeLabel,
  gradesOf,
  cleanQuote,
  lessonName,
  pageRange,
  rememberGrade,
  storedGrade,
  useAlignProjects,
  useProjectAlignments,
  type ProjectAlign,
} from '../components/align/data'
import { scopeOptions, useProjectScope } from '../components/align/scope'
import { AlignTopbar, MatchBadge, RollBadge } from '../components/align/ui'
import { useProject } from '../project/ProjectContext'
import '../components/align/align.css'

type Lens = 'resource' | 'standard'

/** "Alignment" screen of the Align mockup: one alignment, two lenses (by resource / by standard). */
export function AlignmentLensPage({ reloadKey = 0, projectId }: { reloadKey?: number; projectId: string }) {
  const { data, error } = useAlignProjects(reloadKey)
  const { project: activeProject } = useProject()
  const navigate = useNavigate()
  const [params, setParams] = useSearchParams()
  const { scope, setScope, isAll } = useProjectScope(projectId, 'alignment')
  const grade = params.get('grade') || storedGrade()
  const [lens, setLens] = useState<Lens>('resource')
  const all = useMemo(() => data ?? [], [data])

  // One project by default; every project (within the grade filter) when scoped to All projects.
  const shown = useMemo(() => {
    if (!isAll) return all.filter((p) => p.project.id === projectId)
    return all
      .filter((p) => grade === 'all' || p.grade === grade)
      .sort((a, b) => a.project.name.localeCompare(b.project.name))
  }, [all, isAll, projectId, grade])

  const openStandard = (project: ProjectAlign, code: string) => {
    const q = new URLSearchParams({ std: code, pid: project.project.id, from: 'alignment' })
    if (project.state) q.set('state', project.state)
    navigate(`/projects/${projectId}/coverage?${q.toString()}`)
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
        here="Standards alignment"
        scope={{ value: scope, onChange: setScope, options: scopeOptions(all, projectId, activeProject?.name) }}
        grade={isAll ? grade : undefined}
        gradeOptions={gradesOf(all)}
        onGrade={setGrade}
        exportHref={`/projects/${projectId}/exports`}
      />
      <section className="va-screen">
        <div className="phead">
          <span className="eyebrow accent">Your curriculum</span>
          <h1>
            Standards alignment<span className="bluedot">.</span>
          </h1>
          <p className="lede">
            The same alignment, viewed two ways. By resource shows what each lesson earns. By standard shows which
            lessons cover each standard. Use Project in the top bar to switch projects, or choose All projects to see
            every state framework.
          </p>
        </div>

        {error ? <div className="va-error">Could not load alignment data: {error}</div> : null}
        {!data && !error ? <div className="va-loading">Loading alignments…</div> : null}
        {data && !shown.length ? (
          <div className="rv-empty">
            {isAll
              ? `No project has standards output${grade === 'all' ? '' : ` for ${gradeLabel(grade)}`} yet.`
              : 'This project has no alignment results yet. Run the pipeline, or choose All projects.'}
          </div>
        ) : null}

        {shown.length ? (
          <div className="panel">
            <div className="panel-head">
              <div className="filters" role="group" aria-label="Lens">
                <button type="button" className={`chip${lens === 'resource' ? ' on' : ''}`} aria-pressed={lens === 'resource'} onClick={() => setLens('resource')}>
                  By resource
                </button>
                <button type="button" className={`chip${lens === 'standard' ? ' on' : ''}`} aria-pressed={lens === 'standard'} onClick={() => setLens('standard')}>
                  By standard
                </button>
              </div>
              <span className="meta">
                {isAll ? `${shown.length} project${shown.length === 1 ? '' : 's'}` : shown[0].project.name}
              </span>
            </div>
            <div className="panel-body">
              {shown.map((p) => (
                <ProjectLens key={p.project.id} project={p} lens={lens} onOpen={(code) => openStandard(p, code)} />
              ))}
            </div>
          </div>
        ) : null}
        <p className="screen-note">
          Matches come from the alignment judge and point to pages in the teacher guide. Open a standard to see its
          evidence and expert verification.
        </p>
      </section>
    </div>
  )
}

/** One project's alignment under the chosen lens. */
function ProjectLens({ project, lens, onOpen }: { project: ProjectAlign; lens: Lens; onOpen: (code: string) => void }) {
  const rows = useProjectAlignments(project.project.id)
  return (
    <div className="rs-project">
      <div className="rs-fwbar">
        {lens === 'resource' ? 'What each lesson earns against ' : 'Which lessons cover each standard in '}
        <b>{project.state ? STATE_NAMES[project.state] : project.project.name}</b> · {project.framework} ·{' '}
        {gradeLabel(project.grade)}
      </div>
      {rows === null ? (
        <div className="va-loading">Loading alignments…</div>
      ) : lens === 'resource' ? (
        <ByResource project={project} rows={rows} onOpen={onOpen} />
      ) : (
        <ByStandard project={project} rows={rows} onOpen={onOpen} />
      )}
    </div>
  )
}

type Pair = { match: 'full' | 'partial'; rows: AlignmentRow[] }

/** Strongest match across a lesson × standard pair's evidence rows. */
function pairMatch(rows: AlignmentRow[]): 'full' | 'partial' {
  return rows.some((r) => r.matched_status === 'full') ? 'full' : 'partial'
}

const CONFIDENCE_TEXT: Record<string, string> = { high: 'High confidence', medium: 'Medium confidence', low: 'Low confidence' }

/** The judge's evidence for one lesson × one standard, shown in place. */
function PairEvidence({
  rows,
  standardText,
  onOpenAll,
}: {
  rows: AlignmentRow[]
  standardText?: string
  onOpenAll: () => void
}) {
  return (
    <div className="pair-ev" role="region" aria-label="Evidence for this lesson and standard">
      {standardText ? <p className="pair-ev-std">{standardText}</p> : null}
      {rows.map((r) => (
        <div className="pair-ev-item" key={r.id}>
          <div className="pair-ev-top">
            <MatchBadge match={r.matched_status} />
            <span className="pair-ev-page">{r.evidence_page ? pageRange([r.evidence_page]) : 'Teacher guide'}</span>
            {r.confidence ? <span className="pair-ev-conf">{CONFIDENCE_TEXT[r.confidence] ?? r.confidence}</span> : null}
          </div>
          {r.evidence ? <blockquote className="pair-ev-quote">“{cleanQuote(r.evidence)}”</blockquote> : null}
          {r.rationale ? <p className="pair-ev-why">{r.rationale}</p> : null}
        </div>
      ))}
      <button type="button" className="pair-ev-all" onClick={onOpenAll}>
        Compare all lessons for this standard →
      </button>
    </div>
  )
}

function Chevron({ open }: { open: boolean }) {
  return <span className={`rs-chev${open ? ' open' : ''}`} aria-hidden="true" />
}

function ByResource({ project, rows, onOpen }: { project: ProjectAlign; rows: AlignmentRow[]; onOpen: (code: string) => void }) {
  const leafByCode = useMemo(() => new Map(project.leaves.map((l) => [l.code, l])), [project])
  const [openLesson, setOpenLesson] = useState<string | null>(null)
  const [openStd, setOpenStd] = useState<string | null>(null)
  const lessons = useMemo(() => {
    const map = new Map<string, { title: string; pages: number[]; stds: Map<string, AlignmentRow[]> }>()
    rows.forEach((r) => {
      if (r.matched_status === 'none') return
      const entry = map.get(r.resource_id) ?? { title: r.lesson_title, pages: [] as number[], stds: new Map<string, AlignmentRow[]>() }
      if (r.evidence_page) entry.pages.push(r.evidence_page)
      entry.stds.set(r.standard_code, [...(entry.stds.get(r.standard_code) ?? []), r])
      map.set(r.resource_id, entry)
    })
    return [...map.entries()].sort(([a], [b]) => a.localeCompare(b, undefined, { numeric: true }))
  }, [rows])

  if (!lessons.length) return <div className="rv-empty">No lesson aligns to a standard yet.</div>

  return (
    <div className="rs-list">
      <p className="rs-hint">Select a lesson to see the standards it earns, then a standard to see the evidence.</p>
      {lessons.map(([rid, l]) => {
        const stds: [string, Pair][] = [...l.stds.entries()]
          .map(([code, rs]): [string, Pair] => [code, { match: pairMatch(rs), rows: rs }])
          .sort(([a], [b]) => a.localeCompare(b, undefined, { numeric: true }))
        const full = stds.filter(([, p]) => p.match === 'full').length
        const isOpen = openLesson === rid
        return (
          <div className={`rs-card${isOpen ? ' is-open' : ''}`} key={rid}>
            <button
              type="button"
              className="rs-head rs-head-click"
              aria-expanded={isOpen}
              onClick={() => {
                setOpenLesson(isOpen ? null : rid)
                setOpenStd(null)
              }}
            >
              <div>
                <div className="rs-name">{lessonName(rid, l.title)}</div>
                <div className="rs-loc">
                  {pageRange(l.pages)} · {gradeLabel(project.grade)} ELA
                </div>
              </div>
              <div className="rs-sum">
                <div className="rs-sum-n">
                  {stds.length} standard{stds.length === 1 ? '' : 's'}
                </div>
                <div className="rs-sum-d">
                  {full} full · {stds.length - full} partial
                </div>
              </div>
              <Chevron open={isOpen} />
            </button>
            {isOpen
              ? stds.map(([code, pair]) => {
                  const key = `${rid}|${code}`
                  const stdOpen = openStd === key
                  const leaf = leafByCode.get(code)
                  return (
                    <div className="rs-std-wrap" key={code}>
                      <button
                        type="button"
                        className={`rs-std${stdOpen ? ' is-open' : ''}`}
                        aria-expanded={stdOpen}
                        onClick={() => setOpenStd(stdOpen ? null : key)}
                      >
                        <span className="std-code">{code}</span>
                        <span className="rv-strand">{leaf?.domainLabel ?? ''}</span>
                        <span className="rs-right">
                          <MatchBadge match={pair.match} />
                          <span className="drill">{stdOpen ? 'Hide evidence' : 'Evidence'}</span>
                        </span>
                      </button>
                      {stdOpen ? (
                        <PairEvidence rows={pair.rows} standardText={leaf?.text} onOpenAll={() => onOpen(code)} />
                      ) : null}
                    </div>
                  )
                })
              : null}
          </div>
        )
      })}
    </div>
  )
}

function ByStandard({ project, rows, onOpen }: { project: ProjectAlign; rows: AlignmentRow[]; onOpen: (code: string) => void }) {
  const [openStdCode, setOpenStdCode] = useState<string | null>(null)
  const [openPair, setOpenPair] = useState<string | null>(null)
  const lessonsByStd = useMemo(() => {
    const map = new Map<string, Map<string, { title: string; pages: number[]; rows: AlignmentRow[] }>>()
    rows.forEach((r) => {
      if (r.matched_status === 'none') return
      const per = map.get(r.standard_code) ?? new Map<string, { title: string; pages: number[]; rows: AlignmentRow[] }>()
      const entry = per.get(r.resource_id) ?? { title: r.lesson_title, pages: [] as number[], rows: [] as AlignmentRow[] }
      if (r.evidence_page) entry.pages.push(r.evidence_page)
      entry.rows.push(r)
      per.set(r.resource_id, entry)
      map.set(r.standard_code, per)
    })
    return map
  }, [rows])

  return (
    <div className="rs-list">
      <p className="rs-hint">Select a standard to see the lessons that cover it, then a lesson to see the evidence.</p>
      {project.leaves.map((leaf) => {
        const lessons = [...(lessonsByStd.get(leaf.code)?.entries() ?? [])].sort(([a], [b]) =>
          a.localeCompare(b, undefined, { numeric: true }),
        )
        const isOpen = openStdCode === leaf.code
        return (
          <div className={`rs-card${isOpen ? ' is-open' : ''}`} key={leaf.code}>
            <button
              type="button"
              className="rs-head rs-head-click"
              aria-expanded={isOpen}
              onClick={() => {
                setOpenStdCode(isOpen ? null : leaf.code)
                setOpenPair(null)
              }}
            >
              <div>
                <div className="rs-name">
                  {leaf.code} <span className="rv-strand">{leaf.domainLabel}</span>
                </div>
                <div className="rs-loc">{leaf.text}</div>
              </div>
              <div className="rs-sum">
                <RollBadge status={leaf.status} fill />
                <div className="rs-sum-d">
                  {lessons.length} lesson{lessons.length === 1 ? '' : 's'}
                </div>
              </div>
              <Chevron open={isOpen} />
            </button>
            {isOpen ? (
              lessons.length ? (
                lessons.map(([rid, l]) => {
                  const key = `${leaf.code}|${rid}`
                  const pairOpen = openPair === key
                  return (
                    <div className="rs-std-wrap" key={rid}>
                      <button
                        type="button"
                        className={`rs-rsrc rs-rsrc-click${pairOpen ? ' is-open' : ''}`}
                        aria-expanded={pairOpen}
                        onClick={() => setOpenPair(pairOpen ? null : key)}
                      >
                        <span className="rs-rsrc-name">{lessonName(rid, l.title)}</span>
                        <span className="rs-right rs-right-inline">
                          <MatchBadge match={pairMatch(l.rows)} />
                          <span className="rs-rsrc-loc">{pageRange(l.pages)}</span>
                        </span>
                      </button>
                      {pairOpen ? <PairEvidence rows={l.rows} onOpenAll={() => onOpen(leaf.code)} /> : null}
                    </div>
                  )
                })
              ) : (
                <div className="rs-none">No aligned lesson in this curriculum</div>
              )
            ) : null}
          </div>
        )
      })}
    </div>
  )
}

export default AlignmentLensPage
