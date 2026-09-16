import { useEffect, useMemo, useState } from 'react'
import { NavLink, useLocation, useNavigate } from 'react-router-dom'
import { useAuth } from '../../auth/AuthContext'
import { UserAvatar } from '../UserAvatar'
import { NONE_PROJECT_ID, useProject } from '../../project/ProjectContext'
import { SidebarToggleIcon } from './SidebarToggleIcon'

type Props = {
  collapsed: boolean
  onToggle: () => void
}

type Leaf = { label: string; to: string; end?: boolean; needsProject?: boolean }

function IconHome() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden>
      <path d="M4 10.5 12 4l8 6.5V20a1 1 0 0 1-1 1h-5v-6H10v6H5a1 1 0 0 1-1-1v-9.5Z" stroke="currentColor" strokeWidth="1.7" strokeLinejoin="round" />
    </svg>
  )
}
function IconGrid() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden>
      <rect x="4" y="4" width="7" height="7" rx="1.5" stroke="currentColor" strokeWidth="1.7" />
      <rect x="13" y="4" width="7" height="7" rx="1.5" stroke="currentColor" strokeWidth="1.7" />
      <rect x="4" y="13" width="7" height="7" rx="1.5" stroke="currentColor" strokeWidth="1.7" />
      <rect x="13" y="13" width="7" height="7" rx="1.5" stroke="currentColor" strokeWidth="1.7" />
    </svg>
  )
}
function IconAlign() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden>
      <circle cx="12" cy="12" r="7.25" stroke="currentColor" strokeWidth="1.7" />
      <circle cx="12" cy="12" r="2.75" stroke="currentColor" strokeWidth="1.7" />
    </svg>
  )
}
function IconExport() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden>
      <path d="M12 4v10" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" />
      <path d="m8 10 4 4 4-4" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M5 18h14" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" />
    </svg>
  )
}
function IconGear() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden>
      <path
        d="M12 15.2a3.2 3.2 0 1 0 0-6.4 3.2 3.2 0 0 0 0 6.4Z"
        stroke="currentColor"
        strokeWidth="1.7"
      />
      <path
        d="M19.4 13.1c.05-.36.05-.74 0-1.1l1.6-1.25a.4.4 0 0 0 .1-.5l-1.5-2.6a.4.4 0 0 0-.48-.18l-1.88.76a6.1 6.1 0 0 0-.95-.55l-.28-2a.4.4 0 0 0-.4-.34h-3a.4.4 0 0 0-.4.34l-.28 2c-.33.14-.65.32-.95.55l-1.88-.76a.4.4 0 0 0-.48.18l-1.5 2.6a.4.4 0 0 0 .1.5L4.6 12c-.05.36-.05.74 0 1.1L3 14.35a.4.4 0 0 0-.1.5l1.5 2.6c.1.18.3.25.48.18l1.88-.76c.3.23.62.41.95.55l.28 2c.04.2.2.34.4.34h3c.2 0 .36-.14.4-.34l.28-2c.33-.14.65-.32.95-.55l1.88.76c.18.07.38 0 .48-.18l1.5-2.6a.4.4 0 0 0-.1-.5L19.4 13.1Z"
        stroke="currentColor"
        strokeWidth="1.4"
        strokeLinejoin="round"
      />
    </svg>
  )
}
function IconChevron({ open }: { open: boolean }) {
  return (
    <svg
      className={`nav-chevron${open ? ' open' : ''}`}
      width="14"
      height="14"
      viewBox="0 0 24 24"
      fill="none"
      aria-hidden
    >
      <path d="m9 6 6 6-6 6" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

function pathMatches(pathname: string, to: string, end?: boolean) {
  if (end) return pathname === to || pathname === `${to}/`
  return pathname === to || pathname.startsWith(`${to}/`)
}

export function Sidebar({ collapsed, onToggle }: Props) {
  const { projectId, project, hasProject } = useProject()
  const { user, logout } = useAuth()
  const navigate = useNavigate()
  const { pathname } = useLocation()
  const base = hasProject ? `/projects/${projectId}` : `/projects/${NONE_PROJECT_ID}`

  const contentLeaves: Leaf[] = useMemo(
    () => [
      { label: 'Curriculum', to: `${base}/curriculum`, needsProject: true },
      { label: 'Standards', to: `${base}/standards`, needsProject: true },
    ],
    [base],
  )
  const alignmentLeaves: Leaf[] = useMemo(
    () => [
      { label: 'Alignments', to: `${base}/alignments`, needsProject: true },
      { label: 'Review', to: `${base}/review`, needsProject: true },
    ],
    [base],
  )
  const operationsLeaves: Leaf[] = useMemo(
    () => [
      { label: 'Projects', to: `${base}/projects` },
      { label: 'Ingestion', to: `${base}/ingestion` },
      { label: 'Pipeline', to: `${base}/pipeline` },
      { label: 'Logging', to: `${base}/logging` },
    ],
    [base],
  )

  const contentActive = contentLeaves.some((l) => pathMatches(pathname, l.to))
  const alignmentActive = alignmentLeaves.some((l) => pathMatches(pathname, l.to))
  const operationsActive = operationsLeaves.some((l) => pathMatches(pathname, l.to))

  const [open, setOpen] = useState({
    content: contentActive,
    alignment: alignmentActive,
    operations: operationsActive,
  })

  useEffect(() => {
    setOpen((prev) => ({
      content: prev.content || contentActive,
      alignment: prev.alignment || alignmentActive,
      operations: prev.operations || operationsActive,
    }))
  }, [contentActive, alignmentActive, operationsActive])

  const renderLeaf = (leaf: Leaf) => {
    if (leaf.needsProject && !hasProject) {
      return (
        <span key={leaf.label} className="nav-sub nav-soon">
          {leaf.label}
        </span>
      )
    }
    return (
      <NavLink key={leaf.to} to={leaf.to} end={leaf.end} data-nav className="nav-sub">
        {leaf.label}
      </NavLink>
    )
  }

  return (
    <aside className="sidebar" aria-hidden={collapsed}>
      <div className="brand-block">
        <div className="brand-row">
          <a href={hasProject ? base : '/'} className="brand" aria-label="Veramynd home">
            <img className="brand-logo" src="/logo.png" alt="Veramynd" />
          </a>
          <button type="button" className="menu-btn" onClick={onToggle} aria-label="Toggle sidebar" title="Toggle sidebar">
            <SidebarToggleIcon />
          </button>
        </div>
        <div className="brand-project" title={hasProject ? project?.name || 'Project' : 'No project'}>
          {hasProject ? project?.name || 'Project' : 'No project'}
        </div>
      </div>

      <nav className="nav-scroll" aria-label="Main">
        <div className="nav-group">
          <div className="nav-label">Main menu</div>
          <NavLink to={base} end data-nav className="nav-item">
            <span className="nav-ico">
              <IconHome />
            </span>
            <span className="nav-copy">Overview</span>
          </NavLink>
        </div>

        <div className="nav-group">
          <div className="nav-label">Features</div>
          <button
            type="button"
            className={`nav-parent${contentActive ? ' active-section' : ''}${open.content ? ' open' : ''}`}
            aria-expanded={open.content}
            onClick={() => setOpen((s) => ({ ...s, content: !s.content }))}
          >
            <span className="nav-ico">
              <IconGrid />
            </span>
            <span className="nav-copy">Curriculum</span>
            <IconChevron open={open.content} />
          </button>
          {open.content ? <div className="nav-children">{contentLeaves.map(renderLeaf)}</div> : null}
        </div>

        <div className="nav-group">
          <div className="nav-label">Alignment</div>
          <button
            type="button"
            className={`nav-parent${alignmentActive ? ' active-section' : ''}${open.alignment ? ' open' : ''}`}
            aria-expanded={open.alignment}
            onClick={() => setOpen((s) => ({ ...s, alignment: !s.alignment }))}
          >
            <span className="nav-ico">
              <IconAlign />
            </span>
            <span className="nav-copy">Alignment</span>
            <IconChevron open={open.alignment} />
          </button>
          {open.alignment ? <div className="nav-children">{alignmentLeaves.map(renderLeaf)}</div> : null}
        </div>

        <div className="nav-group">
          <div className="nav-label">Output</div>
          <NavLink to={`${base}/exports`} data-nav className="nav-item">
            <span className="nav-ico">
              <IconExport />
            </span>
            <span className="nav-copy">Exports</span>
          </NavLink>
        </div>

        <div className="nav-group">
          <div className="nav-label">Operations</div>
          <button
            type="button"
            className={`nav-parent${operationsActive ? ' active-section' : ''}${open.operations ? ' open' : ''}`}
            aria-expanded={open.operations}
            onClick={() => setOpen((s) => ({ ...s, operations: !s.operations }))}
          >
            <span className="nav-ico">
              <IconGear />
            </span>
            <span className="nav-copy">Operations</span>
            <IconChevron open={open.operations} />
          </button>
          {open.operations ? <div className="nav-children">{operationsLeaves.map(renderLeaf)}</div> : null}
        </div>

        <div className="nav-divider" />

        <div className="nav-group">
          <div className="nav-label">General</div>
          <NavLink to={`${base}/settings`} data-nav className="nav-item">
            <span className="nav-ico">
              <IconGear />
            </span>
            <span className="nav-copy">Settings</span>
          </NavLink>
        </div>
      </nav>

      <div className="sidebar-bottom">
        <div className="user-row" title={user?.email || undefined}>
          <UserAvatar name={user?.name} avatarUrl={user?.avatar_url} />
          <div className="user-meta">
            <div className="user-name">{user?.name || 'Reviewer'}</div>
            <div className="user-role">{user?.email || 'Alignment workspace'}</div>
          </div>
        </div>
        <button
          type="button"
          className="btn ghost logout-btn"
          onClick={() => {
            void (async () => {
              await logout()
              navigate('/login', { replace: true })
            })()
          }}
        >
          Log out
        </button>
      </div>
    </aside>
  )
}
