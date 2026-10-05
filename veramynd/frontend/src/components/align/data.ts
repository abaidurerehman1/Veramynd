// Shared data layer for the macro → micro alignment views (national → state → domain → standard → evidence).
import { useCallback, useEffect, useState } from 'react'
import { api, withProject } from '../../api/client'
import type { AlignmentRow, ProjectCard, ProjectsResponse, ReviewItem, StandardCoverageRow } from '../../api/types'

export type RollUp = 'met' | 'partial' | 'gap'

/** A leaf standard (the level alignments are judged at) with its roll-up status. */
export type LeafStandard = {
  code: string
  text: string
  domainCode: string
  domainLabel: string
  groupLabel: string // big idea / strand label, e.g. "Fluency"
  status: RollUp
  lessons: string[]
  full: number
  partial: number
}

export type Domain = { code: string; label: string }

/** One project = one curriculum aligned to one state framework and grade. */
export type ProjectAlign = {
  project: ProjectCard
  state: string | null // USPS code, e.g. "GA"
  framework: string
  grade: string // "K", "1", … or "" when unknown
  domains: Domain[]
  leaves: LeafStandard[]
}

export type Agg = { total: number; met: number; partial: number; gap: number; coverage: number }

export const STATE_NAMES: Record<string, string> = {
  AK: 'Alaska', AL: 'Alabama', AR: 'Arkansas', AZ: 'Arizona', CA: 'California', CO: 'Colorado',
  CT: 'Connecticut', DE: 'Delaware', FL: 'Florida', GA: 'Georgia', HI: 'Hawaii', IA: 'Iowa',
  ID: 'Idaho', IL: 'Illinois', IN: 'Indiana', KS: 'Kansas', KY: 'Kentucky', LA: 'Louisiana',
  MA: 'Massachusetts', MD: 'Maryland', ME: 'Maine', MI: 'Michigan', MN: 'Minnesota', MO: 'Missouri',
  MS: 'Mississippi', MT: 'Montana', NC: 'North Carolina', ND: 'North Dakota', NE: 'Nebraska',
  NH: 'New Hampshire', NJ: 'New Jersey', NM: 'New Mexico', NV: 'Nevada', NY: 'New York', OH: 'Ohio',
  OK: 'Oklahoma', OR: 'Oregon', PA: 'Pennsylvania', RI: 'Rhode Island', SC: 'South Carolina',
  SD: 'South Dakota', TN: 'Tennessee', TX: 'Texas', UT: 'Utah', VA: 'Virginia', VT: 'Vermont',
  WA: 'Washington', WI: 'Wisconsin', WV: 'West Virginia', WY: 'Wyoming',
}
export const STATE_CODES = Object.keys(STATE_NAMES)

/** "GA ELA" → "GA"; "Texas TEKS" → "TX"; unknown → null. */
export function stateFromFramework(framework: string): string | null {
  const fw = (framework || '').trim()
  if (!fw) return null
  const first = fw.split(/[\s_\-·.]+/)[0].toUpperCase()
  if (STATE_NAMES[first]) return first
  const lower = fw.toLowerCase()
  const byName = STATE_CODES.find((c) => lower.includes(STATE_NAMES[c].toLowerCase()))
  return byName ?? null
}

export function gradeLabel(g: string) {
  if (g === 'all') return 'All grades'
  if (!g) return 'Grade —'
  return g === 'K' ? 'Kindergarten' : `Grade ${g}`
}

export function statusFromCoverage(status: string): RollUp {
  if (status === 'covered') return 'met'
  if (status === 'partial') return 'partial'
  return 'gap'
}

export function aggregate(leaves: LeafStandard[]): Agg {
  const a = { total: leaves.length, met: 0, partial: 0, gap: 0, coverage: 0 }
  leaves.forEach((l) => {
    a[l.status] += 1
  })
  a.coverage = a.total ? Math.round((100 * a.met) / a.total) : 0
  return a
}

/** Rounded shares that always sum to 100. */
export function shares(a: { met: number; partial: number; gap: number }) {
  const tot = a.met + a.partial + a.gap || 1
  let m = Math.round((100 * a.met) / tot)
  let g = Math.round((100 * a.gap) / tot)
  let p = 100 - m - g
  if (p < 0) {
    if (m >= g) m += p
    else g += p
    p = 0
  }
  return { m, p, g }
}

type TreeNode = { code: string; level: string; label: string; text: string; children?: TreeNode[] }

function buildProjectAlign(project: ProjectCard, roots: TreeNode[], coverage: StandardCoverageRow[]): ProjectAlign {
  const byCode = new Map(coverage.map((r) => [r.code, r]))
  const domains: Domain[] = roots.map((r) => ({ code: r.code, label: r.label || r.code }))
  const leaves: LeafStandard[] = []

  const walk = (node: TreeNode, domain: Domain, group: string) => {
    const kids = node.children ?? []
    const nextGroup = node.level === 'big_idea' || node.level === 'strand' ? node.label || group : group
    if (!kids.length && node.level !== 'domain') {
      const cov = byCode.get(node.code)
      leaves.push({
        code: node.code,
        text: node.text,
        domainCode: domain.code,
        domainLabel: domain.label,
        groupLabel: nextGroup,
        status: statusFromCoverage(cov?.status ?? 'not_found'),
        lessons: cov?.lessons ?? [],
        full: cov?.full ?? 0,
        partial: cov?.partial ?? 0,
      })
      return
    }
    kids.forEach((k) => walk(k, domain, nextGroup))
  }
  roots.forEach((r, i) => walk(r, domains[i], ''))

  return {
    project,
    state: stateFromFramework(project.framework),
    framework: project.framework,
    grade: project.grade == null ? '' : String(project.grade),
    domains,
    leaves,
  }
}

// ---- module-level caches so every page shares one fetch per project ----
let projectsPromise: Promise<ProjectAlign[]> | null = null
const alignmentCache = new Map<string, Promise<AlignmentRow[]>>()

async function loadAllProjects(): Promise<ProjectAlign[]> {
  const { projects } = await api<ProjectsResponse>('/api/projects')
  const results = await Promise.all(
    projects.map(async (project) => {
      try {
        const [tree, cov] = await Promise.all([
          api<{ roots: TreeNode[] }>(withProject('/api/standards/tree', project.id)),
          api<{ rows: StandardCoverageRow[] }>(withProject('/api/standards/coverage', project.id)),
        ])
        if (!tree.roots?.length) return null
        return buildProjectAlign(project, tree.roots, cov.rows)
      } catch {
        return null // projects without standards output yet
      }
    }),
  )
  return results.filter((r): r is ProjectAlign => r !== null)
}

export function invalidateAlignData() {
  projectsPromise = null
  alignmentCache.clear()
}

/** Every project that has standards output, with leaf roll-ups. */
export function useAlignProjects(reloadKey = 0) {
  const [data, setData] = useState<ProjectAlign[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    if (reloadKey) invalidateAlignData()
    if (!projectsPromise) projectsPromise = loadAllProjects()
    projectsPromise
      .then((d) => !cancelled && setData(d))
      .catch((e) => {
        projectsPromise = null
        if (!cancelled) setError(e instanceof Error ? e.message : String(e))
      })
    return () => {
      cancelled = true
    }
  }, [reloadKey])

  return { data, error }
}

/** All judged lesson × standard pairs for one project. */
export function useProjectAlignments(projectId: string | null) {
  const [rows, setRows] = useState<AlignmentRow[] | null>(null)

  useEffect(() => {
    if (!projectId) {
      setRows(null)
      return
    }
    let cancelled = false
    let p = alignmentCache.get(projectId)
    if (!p) {
      p = api<{ rows: AlignmentRow[] }>(withProject('/api/alignments?limit=2000', projectId)).then((d) => d.rows)
      alignmentCache.set(projectId, p)
    }
    p.then((r) => !cancelled && setRows(r)).catch(() => {
      alignmentCache.delete(projectId)
      if (!cancelled) setRows([])
    })
    return () => {
      cancelled = true
    }
  }, [projectId])

  return rows
}

// ---- SME review decisions ----

export type Decision = { item_id: string; decision: 'accepted' | 'rejected'; reviewer: string; decided_at: string | null }
export type DecisionMap = Record<string, Decision>

// Decisions live in one module-level store so every screen (and the sidebar count) sees a change at once.
const decisionStore: Record<string, DecisionMap> = {}
const decisionLoads = new Map<string, Promise<boolean>>()
const decisionListeners = new Set<() => void>()
let decisionsAvailable = true
const notifyDecisions = () => decisionListeners.forEach((fn) => fn())

function loadDecisions(id: string) {
  let p = decisionLoads.get(id)
  if (!p) {
    p = api<{ decisions: DecisionMap; available?: boolean }>(`/api/review/decisions?project_id=${encodeURIComponent(id)}`)
      .then((d) => {
        decisionStore[id] = d.decisions ?? {}
        return d.available !== false
      })
      .catch(() => {
        decisionStore[id] = decisionStore[id] ?? {}
        return false
      })
    decisionLoads.set(id, p)
  }
  return p
}

export function useReviewDecisions(projectIds: string[]) {
  const key = projectIds.join('|')
  const [, setTick] = useState(0)
  const [available, setAvailable] = useState(decisionsAvailable)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const listener = () => setTick((t) => t + 1)
    decisionListeners.add(listener)
    return () => {
      decisionListeners.delete(listener)
    }
  }, [])

  useEffect(() => {
    let cancelled = false
    const ids = key ? key.split('|') : []
    Promise.all(ids.map(loadDecisions)).then((oks) => {
      if (cancelled) return
      decisionsAvailable = oks.every(Boolean)
      setAvailable(decisionsAvailable)
      setTick((t) => t + 1)
    })
    return () => {
      cancelled = true
    }
  }, [key])

  const decisions: Record<string, DecisionMap> = {}
  ;(key ? key.split('|') : []).forEach((id) => {
    if (decisionStore[id]) decisions[id] = decisionStore[id]
  })

  const decide = useCallback(
    async (projectId: string, itemId: string, decision: 'accepted' | 'rejected' | 'pending') => {
      setError(null)
      const res = await fetch('/api/review/decisions', {
        method: 'PUT',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ project_id: projectId, item_id: itemId, decision }),
      })
      if (!res.ok) {
        const msg = res.status === 401 ? 'Sign in again to record review decisions.' : await res.text()
        setError(msg || `HTTP ${res.status}`)
        return
      }
      const body = (await res.json()) as { decision: Decision | null }
      const next = { ...(decisionStore[projectId] ?? {}) }
      if (body.decision) next[itemId] = body.decision
      else delete next[itemId]
      decisionStore[projectId] = next
      notifyDecisions()
    },
    [],
  )

  return { decisions, available, error, decide }
}

// ---- SME review queue (flagged citations per project) ----

const queueCache = new Map<string, Promise<ReviewItem[]>>()

/** Flagged citations for each project, keyed by project id. */
export function useReviewQueue(projectIds: string[], reloadKey = 0) {
  const key = projectIds.join('|')
  const [rows, setRows] = useState<Record<string, ReviewItem[]> | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    if (reloadKey) queueCache.clear()
    const ids = key ? key.split('|') : []
    Promise.all(
      ids.map((id) => {
        let p = queueCache.get(id)
        if (!p) {
          p = api<{ rows: ReviewItem[] }>(withProject('/api/review', id)).then((d) => d.rows || [])
          queueCache.set(id, p)
        }
        return p
          .then((r) => [id, r] as const)
          .catch((e) => {
            queueCache.delete(id)
            if (!cancelled) setError(e instanceof Error ? e.message : String(e))
            return [id, [] as ReviewItem[]] as const
          })
      }),
    ).then((pairs) => !cancelled && setRows(Object.fromEntries(pairs)))
    return () => {
      cancelled = true
    }
  }, [key, reloadKey])

  return { rows, error }
}

// ---- Grade filter shared by every Engagement screen (like the mockup's global grade select) ----

const GRADE_KEY = 'veramynd.alignGrade'

export function storedGrade() {
  try {
    return sessionStorage.getItem(GRADE_KEY) || 'all'
  } catch {
    return 'all'
  }
}

/** Grades present across projects, in school order (K first). */
export function gradesOf(projects: ProjectAlign[]) {
  return [...new Set(projects.map((p) => p.grade).filter(Boolean))].sort((a, b) =>
    a === 'K' ? -1 : b === 'K' ? 1 : Number(a) - Number(b),
  )
}

export function rememberGrade(grade: string) {
  try {
    sessionStorage.setItem(GRADE_KEY, grade)
  } catch {
    /* storage blocked: the grade still applies through the URL */
  }
}

/** "G1M2U1L1" + "Lesson 1: Noticing…" → "Unit 1, Lesson 1 — Noticing…". */
export function lessonName(resourceId: string, title?: string) {
  const m = /U(\d+)L(\d+)/i.exec(resourceId)
  const clean = (title || '').replace(/^Lesson\s+\d+\s*:\s*/i, '').trim()
  if (!m) return clean || resourceId
  return `Unit ${m[1]}, Lesson ${m[2]}${clean ? ` — ${clean}` : ''}`
}

export function pageRange(pages: number[]) {
  const ps = [...new Set(pages.filter((p) => Number.isFinite(p)))].sort((a, b) => a - b)
  if (!ps.length) return 'Teacher guide'
  return ps.length === 1 ? `Teacher guide, p. ${ps[0]}` : `Teacher guide, pp. ${ps[0]}–${ps[ps.length - 1]}`
}

/**
 * Turn the judge's machine review reason into a short headline and a readable note, e.g.
 * "cross-lesson inconsistency: X labels={'full': 1, 'none': 1} peers=['G1M2U1L3', …]" or
 * "none-or-partial — explanation; confidence=low".
 */
export function describeReviewReason(raw: string): { headline: string; note: string } {
  const text = (raw || '').trim()
  const cross = /^cross-lesson inconsistency/i.exec(text)
  if (cross) {
    const labels = [...text.matchAll(/'(full|partial|none)':\s*(\d+)/g)].map((m) => `${m[2]} ${m[1]}`)
    const peers = [...text.matchAll(/'([A-Z0-9]*U\d+L\d+)'/gi)].map((m) => lessonName(m[1]))
    return {
      headline: 'Judged differently across lessons',
      note: `${labels.length ? `Verdicts: ${labels.join(', ')}` : 'Verdicts disagree'}${peers.length ? ` (${peers.join(' and ')})` : ''}.`,
    }
  }
  const borderline = /^(full|partial|none)-or-(full|partial|none)\s*[—-]\s*/i.exec(text)
  if (borderline) {
    const note = text
      .slice(borderline[0].length)
      .replace(/;?\s*confidence=\w+\.?$/i, '')
      .trim()
    return {
      headline: `Borderline: ${borderline[1].toLowerCase()} or ${borderline[2].toLowerCase()}`,
      note: note ? note[0].toUpperCase() + note.slice(1) : '',
    }
  }
  return { headline: text || 'Flagged for review', note: '' }
}

/** Evidence quotes sometimes arrive wrapped in their own quote marks; drop them before re-quoting. */
export function cleanQuote(text: string) {
  return (text || '').trim().replace(/^["“”']+|["“”']+$/g, '').trim()
}
