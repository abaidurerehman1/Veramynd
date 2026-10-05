import { useEffect, useMemo, useState } from 'react'
import { NavLink, useLocation, useNavigate } from 'react-router-dom'
import { useAuth } from '../../auth/AuthContext'
import { UserAvatar } from '../UserAvatar'
import { NONE_PROJECT_ID, useProject } from '../../project/ProjectContext'
import { SidebarToggleIcon } from './SidebarToggleIcon'
import { Wordmark } from './Wordmark'
import { gradeLabel, useReviewDecisions, useReviewQueue } from '../align/data'

type Props = {
  collapsed: boolean
  onToggle: () => void
}

type Leaf = { label: string; to: string; end?: boolean; needsProject?: boolean }

// One icon set for every row: 18px, 1.6 stroke, round joins.
function Svg({ children }: { children: React.ReactNode }) {
  return (
    <svg
      width="18"
      height="18"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.6"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden
    >
      {children}
    </svg>
  )
}
function IconHome() {
  return (
    <Svg>
      <path d="M4 10.5 12 4l8 6.5V20h-5v-6H9v6H4z" />
    </Svg>
  )
}
function IconMap() {
  return (
    <Svg>
      <path d="m3.5 6.5 5.5-2.5 6 2.5 5.5-2.5v13.5l-5.5 2.5-6-2.5-5.5 2.5z" />
      <path d="M9 4v13.5M15 6.5V20" />
    </Svg>
  )
}
function IconAlign() {
  return (
    <Svg>
      <circle cx="9" cy="12" r="5.5" />
      <circle cx="15" cy="12" r="5.5" />
    </Svg>
  )
}
function IconReview() {
  return (
    <Svg>
      <path d="M12 3.5 19 6v5.5c0 4.2-3 7.4-7 9-4-1.6-7-4.8-7-9V6z" />
      <path d="m9 12 2.2 2.2L15.5 10" />
    </Svg>
  )
}
function IconExport() {
  return (
    <Svg>
      <path d="M12 4v10M8 10l4 4 4-4M5 19h14" />
    </Svg>
  )
}
function IconOps() {
  return (
    <Svg>
      <rect x="4" y="4.5" width="16" height="6" rx="1.5" />
      <rect x="4" y="13.5" width="16" height="6" rx="1.5" />
      <path d="M7.5 7.5h.01M7.5 16.5h.01" />
    </Svg>
  )
}
function IconGear() {
  return (
    <Svg>
      <circle cx="12" cy="12" r="3" />
      <path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z" />
    </Svg>
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

  const reviewIds = useMemo(() => (hasProject ? [projectId] : []), [hasProject, projectId])
  const { rows: queue } = useReviewQueue(reviewIds)
  const { decisions } = useReviewDecisions(reviewIds)
  // Matches the SME review page's default view: the selected project's queue.
  const pendingReview = (queue?.[projectId] ?? []).filter((r) => !decisions[projectId]?.[r.id]).length

  const engagement = [
    { label: 'National overview', to: `${base}/coverage`, icon: <IconMap /> },
    { label: 'Alignment', to: `${base}/alignment`, icon: <IconAlign /> },
    { label: 'SME review', to: `${base}/review`, icon: <IconReview />, tag: queue ? pendingReview : null },
  ]
  const operationsLeaves: Leaf[] = useMemo(
    () => [
      { label: 'Projects', to: `${base}/projects` },
      { label: 'Ingestion', to: `${base}/ingestion` },
      { label: 'Pipeline', to: `${base}/pipeline` },
      { label: 'Logging', to: `${base}/logging` },
    ],
    [base],
  )

  const operationsActive = operationsLeaves.some((l) => pathMatches(pathname, l.to))

  const [open, setOpen] = useState({ operations: operationsActive })

  useEffect(() => {
    setOpen((prev) => ({ operations: prev.operations || operationsActive }))
  }, [operationsActive])

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
            <Wordmark size={20} product="Align" />
          </a>
          <button type="button" className="menu-btn" onClick={onToggle} aria-label="Toggle sidebar" title="Toggle sidebar">
            <SidebarToggleIcon />
          </button>
        </div>
        <div className="sidebar-sub">Standards alignment</div>
      </div>

      <nav className="nav-scroll" aria-label="Main">
        <div className="nav-group">
          <div className="nav-label">Workspace</div>
          <NavLink to={base} end data-nav className="nav-item">
            <span className="nav-ico">
              <IconHome />
            </span>
            <span className="nav-copy">Dashboard</span>
          </NavLink>
        </div>

        <div className="nav-group">
          <div className="nav-label">Engagement</div>
          {engagement.map((item) =>
            hasProject ? (
              <NavLink key={item.label} to={item.to} data-nav className="nav-item">
                <span className="nav-ico">{item.icon}</span>
                <span className="nav-copy">{item.label}</span>
                {item.tag != null ? (
                  <span className="nav-tag" aria-label={`${item.tag} awaiting review`}>
                    {item.tag}
                  </span>
                ) : null}
              </NavLink>
            ) : (
              <span key={item.label} className="nav-item nav-soon" aria-disabled="true">
                <span className="nav-ico">{item.icon}</span>
                <span className="nav-copy">{item.label}</span>
              </span>
            ),
          )}
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
            className={`nav-item nav-parent${operationsActive ? ' active-section' : ''}${open.operations ? ' open' : ''}`}
            aria-expanded={open.operations}
            onClick={() => setOpen((s) => ({ ...s, operations: !s.operations }))}
          >
            <span className="nav-ico">
              <IconOps />
            </span>
            <span className="nav-copy">Operations</span>
            <IconChevron open={open.operations} />
          </button>
          {open.operations ? <div className="nav-children">{operationsLeaves.map(renderLeaf)}</div> : null}
        </div>

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

      {hasProject && project ? (
        <div className="sidebar-foot">
          <strong>{project.name}</strong>
          <br />
          <span>
            {[project.framework, project.grade != null ? gradeLabel(String(project.grade)) : null].filter(Boolean).join(' · ') ||
              'Curriculum project'}
          </span>
          <br />
          <span className="muted">Reviewed by a curriculum expert</span>
        </div>
      ) : null}

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
