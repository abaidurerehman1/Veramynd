import { useEffect, useMemo, useRef, useState } from 'react'
import type { ProjectCard } from '../../api/types'
import { NONE_PROJECT_ID, useProject } from '../../project/ProjectContext'

export function projectShortLabel(p: ProjectCard): string {
  const grade = p.grade != null ? `Grade ${p.grade}` : ''
  const subject = (p.subject || '').trim()
  const right = [grade, subject].filter(Boolean).join(' ')
  const left = (p.framework || p.publisher || p.name || 'Project').trim()
  return right ? `${left} · ${right}` : left
}

export function ProjectSwitcher() {
  const { projects, project, projectId, setProjectId, clearProject } = useProject()
  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState('')
  const rootRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  const noneSelected = !projectId || projectId === NONE_PROJECT_ID
  const label = noneSelected ? 'None' : project ? projectShortLabel(project) : 'Select project'

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase()
    if (!q) return projects
    return projects.filter((p) => {
      const hay = [
        p.name,
        p.framework,
        p.publisher,
        p.subject,
        p.module,
        p.grade != null ? `grade ${p.grade}` : '',
        projectShortLabel(p),
      ]
        .join(' ')
        .toLowerCase()
      return hay.includes(q)
    })
  }, [projects, query])

  const showNoneOption = (() => {
    const q = query.trim().toLowerCase()
    if (!q) return true
    return 'none'.startsWith(q) || 'no project'.startsWith(q)
  })()

  useEffect(() => {
    if (!open) return
    const onDoc = (e: MouseEvent) => {
      if (!rootRef.current?.contains(e.target as Node)) setOpen(false)
    }
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setOpen(false)
    }
    document.addEventListener('mousedown', onDoc)
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('mousedown', onDoc)
      document.removeEventListener('keydown', onKey)
    }
  }, [open])

  useEffect(() => {
    if (open) {
      setQuery('')
      requestAnimationFrame(() => inputRef.current?.focus())
    }
  }, [open])

  return (
    <div className={`project-switcher${open ? ' open' : ''}`} ref={rootRef}>
      <button
        type="button"
        className="project-switcher-trigger"
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-label="Search and switch project"
        onClick={() => setOpen((v) => !v)}
      >
        <span className="project-switcher-label">{label}</span>
        <svg className="project-switcher-caret" width="10" height="6" viewBox="0 0 10 6" aria-hidden>
          <path d="M1 1.2 5 4.8 9 1.2" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      </button>

      {open ? (
        <div className="project-switcher-panel" role="listbox" aria-label="Projects">
          <div className="project-switcher-search">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" aria-hidden>
              <circle cx="11" cy="11" r="6.5" stroke="currentColor" strokeWidth="1.8" />
              <path d="M16.5 16.5 20 20" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
            </svg>
            <input
              ref={inputRef}
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search projects…"
              aria-label="Search projects"
            />
          </div>
          <div className="project-switcher-list">
            {showNoneOption ? (
              <button
                type="button"
                role="option"
                aria-selected={noneSelected}
                className={`project-switcher-option project-switcher-none${noneSelected ? ' active' : ''}`}
                onClick={() => {
                  clearProject()
                  setOpen(false)
                }}
              >
                <span className="pso-title">None</span>
                <span className="pso-meta">upload a new project</span>
              </button>
            ) : null}
            {filtered.length === 0 && !showNoneOption ? (
              <div className="project-switcher-empty">No matching projects</div>
            ) : (
              filtered.map((p) => {
                const active = p.id === projectId
                return (
                  <button
                    key={p.id}
                    type="button"
                    role="option"
                    aria-selected={active}
                    className={`project-switcher-option${active ? ' active' : ''}`}
                    onClick={() => {
                      setProjectId(p.id)
                      setOpen(false)
                    }}
                  >
                    <span className="pso-title">{projectShortLabel(p)}</span>
                    <span className="pso-meta">
                      {p.source === 'upload' ? 'Upload · ' : ''}
                      {p.name}
                      {p.has_output ? ' · alignments ready' : ' · no output yet'}
                    </span>
                  </button>
                )
              })
            )}
          </div>
        </div>
      ) : null}
    </div>
  )
}
