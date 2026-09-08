import { NavLink } from 'react-router-dom'
import { NONE_PROJECT_ID, useProject } from '../../project/ProjectContext'
import { SidebarToggleIcon } from './SidebarToggleIcon'

type Props = {
  collapsed: boolean
  onToggle: () => void
}

export function Sidebar({ collapsed, onToggle }: Props) {
  const { projectId, project, hasProject } = useProject()
  const base = hasProject
    ? `/projects/${projectId}`
    : `/projects/${NONE_PROJECT_ID}`

  return (
    <aside className="sidebar" aria-hidden={collapsed}>
      <div className="brand-row">
        <a href={hasProject ? base : '/'} className="brand" aria-label="Veramynd home">
          <img className="brand-logo" src="/logo.png" alt="veramynd" width={168} height={40} />
        </a>
        <button type="button" className="menu-btn" onClick={onToggle} aria-label="Toggle sidebar" title="Toggle sidebar">
          <SidebarToggleIcon />
        </button>
      </div>

      <nav className="nav-scroll" aria-label="Main">
        <div className="nav-group">
          <div className="nav-label">Main</div>
          <div className="nav-project-name" title={project?.name || 'No project'}>
            {hasProject ? project?.name || '…' : 'No project selected'}
          </div>
          <NavLink to={base} end data-nav>
            Overview
          </NavLink>
          {hasProject ? (
            <>
              <NavLink to={`${base}/curriculum`} data-nav>
                Curriculum
              </NavLink>
              <NavLink to={`${base}/standards`} data-nav>
                Standards
              </NavLink>
              <NavLink to={`${base}/alignments`} data-nav>
                Alignments
              </NavLink>
            </>
          ) : (
            <>
              <span className="nav-soon">Curriculum</span>
              <span className="nav-soon">Standards</span>
              <span className="nav-soon">Alignments</span>
            </>
          )}
        </div>
        <div className="nav-group">
          <div className="nav-label">Coming next</div>
          <span className="nav-soon">Ingest</span>
          <span className="nav-soon">Pipeline</span>
        </div>
      </nav>

      <div className="sidebar-bottom">
        <div className="user-row">
          <div className="avatar">VR</div>
          <div className="user-meta">
            <div className="user-name">Reviewer</div>
            <div className="user-role">Project overview</div>
          </div>
        </div>
      </div>
    </aside>
  )
}
