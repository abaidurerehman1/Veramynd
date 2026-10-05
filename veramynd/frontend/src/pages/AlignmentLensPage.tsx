import { useMemo, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import type { AlignmentRow } from '../api/types'
import {
  STATE_NAMES,
  gradeLabel,
  gradesOf,
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

function ByResource({ project, rows, onOpen }: { project: ProjectAlign; rows: AlignmentRow[]; onOpen: (code: string) => void }) {
  const leafByCode = useMemo(() => new Map(project.leaves.map((l) => [l.code, l])), [project])
  const lessons = useMemo(() => {
    const map = new Map<string, { title: string; pages: number[]; stds: Map<string, 'full' | 'partial'> }>()
    rows.forEach((r) => {
      if (r.matched_status === 'none') return
      const entry = map.get(r.resource_id) ?? {
        title: r.lesson_title,
        pages: [] as number[],
        stds: new Map<string, 'full' | 'partial'>(),
      }
      if (r.evidence_page) entry.pages.push(r.evidence_page)
      if (entry.stds.get(r.standard_code) !== 'full') entry.stds.set(r.standard_code, r.matched_status)
      map.set(r.resource_id, entry)
    })
    return [...map.entries()].sort(([a], [b]) => a.localeCompare(b, undefined, { numeric: true }))
  }, [rows])

  if (!lessons.length) return <div className="rv-empty">No lesson aligns to a standard yet.</div>

  return (
    <div className="rs-list">
      {lessons.map(([rid, l]) => {
        const stds = [...l.stds.entries()].sort(([a], [b]) => a.localeCompare(b, undefined, { numeric: true }))
        const full = stds.filter(([, m]) => m === 'full').length
        return (
          <div className="rs-card" key={rid}>
            <div className="rs-head">
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
            </div>
            {stds.map(([code, match]) => (
              <button type="button" className="rs-std" key={code} onClick={() => onOpen(code)}>
                <span className="std-code">{code}</span>
                <span className="rv-strand">{leafByCode.get(code)?.domainLabel ?? ''}</span>
                <span className="rs-right">
                  <MatchBadge match={match} />
                  <span className="drill">Evidence →</span>
                </span>
              </button>
            ))}
          </div>
        )
      })}
    </div>
  )
}

function ByStandard({ project, rows, onOpen }: { project: ProjectAlign; rows: AlignmentRow[]; onOpen: (code: string) => void }) {
  const lessonsByStd = useMemo(() => {
    const map = new Map<string, Map<string, { title: string; pages: number[] }>>()
    rows.forEach((r) => {
      if (r.matched_status === 'none') return
      const per = map.get(r.standard_code) ?? new Map<string, { title: string; pages: number[] }>()
      const entry = per.get(r.resource_id) ?? { title: r.lesson_title, pages: [] as number[] }
      if (r.evidence_page) entry.pages.push(r.evidence_page)
      per.set(r.resource_id, entry)
      map.set(r.standard_code, per)
    })
    return map
  }, [rows])

  return (
    <div className="rs-list">
      {project.leaves.map((leaf) => {
        const lessons = [...(lessonsByStd.get(leaf.code)?.entries() ?? [])].sort(([a], [b]) =>
          a.localeCompare(b, undefined, { numeric: true }),
        )
        const open = leaf.status !== 'gap'
        const head = (
          <>
            <div>
              <div className="rs-name">
                {leaf.code} <span className="rv-strand">{leaf.domainLabel}</span>
              </div>
              <div className="rs-loc">{leaf.text}</div>
            </div>
            <div className="rs-sum">
              <RollBadge status={leaf.status} fill />
              {open ? (
                <div className="rs-evlink">
                  <span className="drill">Evidence →</span>
                </div>
              ) : null}
            </div>
          </>
        )
        return (
          <div className="rs-card" key={leaf.code}>
            {open ? (
              <button type="button" className="rs-head rs-head-click" onClick={() => onOpen(leaf.code)}>
                {head}
              </button>
            ) : (
              <div className="rs-head">{head}</div>
            )}
            {lessons.length ? (
              lessons.map(([rid, l]) => (
                <div className="rs-rsrc" key={rid}>
                  <span className="rs-rsrc-name">{lessonName(rid, l.title)}</span>
                  <span className="rs-rsrc-loc">{pageRange(l.pages)}</span>
                </div>
              ))
            ) : (
              <div className="rs-none">No aligned lesson in this curriculum</div>
            )}
          </div>
        )
      })}
    </div>
  )
}

export default AlignmentLensPage
