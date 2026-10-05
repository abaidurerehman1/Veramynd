import { useNavigate, useSearchParams } from 'react-router-dom'
import { STATE_NAMES, type ProjectAlign } from './data'

/**
 * Alignment and SME review follow the selected project; `?scope=all` widens them to every project.
 * Picking a single project switches the active project (same route, new project id).
 */
export function useProjectScope(projectId: string, page: 'alignment' | 'review') {
  const [params, setParams] = useSearchParams()
  const navigate = useNavigate()
  const scope = params.get('scope') === 'all' ? 'all' : projectId

  const setScope = (value: string) => {
    if (value === 'all') {
      const next = new URLSearchParams(params)
      next.set('scope', 'all')
      setParams(next)
    } else {
      navigate(`/projects/${value}/${page}`)
    }
  }

  return { scope, setScope, isAll: scope === 'all' }
}

/** Options for the topbar Project select: All projects, then each project with results. */
export function scopeOptions(projects: ProjectAlign[], projectId: string, projectName?: string) {
  const opts = [...projects]
    .sort((a, b) => a.project.name.localeCompare(b.project.name))
    .map((p) => ({
      value: p.project.id,
      label: p.state ? `${p.project.name} (${STATE_NAMES[p.state]})` : p.project.name,
    }))
  // The selected project may have no alignment output yet; keep it selectable so the page can say so.
  if (projectId && !opts.some((o) => o.value === projectId)) {
    opts.unshift({ value: projectId, label: `${projectName || projectId} (no results yet)` })
  }
  return [{ value: 'all', label: 'All projects' }, ...opts]
}
