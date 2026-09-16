import { useAuth } from '../../auth/AuthContext'
import { ProjectSwitcher } from './ProjectSwitcher'
import { SidebarToggleIcon } from './SidebarToggleIcon'

type Props = {
  crumbs: string
  showMenu: boolean
  onToggle: () => void
  onReload?: () => void | Promise<void>
}

export function Topbar({ showMenu, onToggle, onReload }: Props) {
  const { user } = useAuth()
  const firstName = (user?.name || 'there').split(/\s+/)[0]

  return (
    <header className="app-header" role="banner">
      <div className="app-header-inner">
        <div className="greet">
          {showMenu && (
            <button type="button" className="menu-btn top-menu" onClick={onToggle} aria-label="Toggle sidebar" title="Toggle sidebar">
              <SidebarToggleIcon />
            </button>
          )}
          <div className="greet-copy">
            <h1 className="greet-title">Welcome back, {firstName}</h1>
            <p className="greet-sub">Here is your alignment workspace summary.</p>
          </div>
        </div>
        <div className="top-actions">
          <button
            type="button"
            className="icon-btn refresh-btn"
            title="Refresh data"
            aria-label="Refresh data"
            onClick={() => void onReload?.()}
          >
            <svg className="refresh-icon" width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden>
              <path d="M21 12a9 9 0 0 0-15.36-6.36" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" />
              <path d="M5.5 3.5v4.2h4.2" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" />
              <path d="M3 12a9 9 0 0 0 15.36 6.36" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" />
              <path d="M18.5 20.5v-4.2h-4.2" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </button>
          <ProjectSwitcher />
        </div>
      </div>
    </header>
  )
}
