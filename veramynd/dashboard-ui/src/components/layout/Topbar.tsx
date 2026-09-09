import { greeting } from '../../lib/format'
import { ProjectSwitcher } from './ProjectSwitcher'
import { SidebarToggleIcon } from './SidebarToggleIcon'

type Props = {
  crumbs: string
  showMenu: boolean
  onToggle: () => void
  onReload?: () => void | Promise<void>
}

export function Topbar({ crumbs, showMenu, onToggle, onReload }: Props) {
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
            <h1 className="greet-title">{greeting()}</h1>
            <p className="greet-sub">{crumbs}</p>
          </div>
        </div>
        <div className="top-actions">
          <ProjectSwitcher />
          <button
            type="button"
            className="icon-btn refresh-btn"
            title="Refresh overview"
            aria-label="Refresh overview"
            onClick={() => void onReload?.()}
          >
            <svg className="refresh-icon" width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden>
              <path
                d="M21 12a9 9 0 0 0-15.36-6.36"
                stroke="currentColor"
                strokeWidth="1.75"
                strokeLinecap="round"
              />
              <path
                d="M5.5 3.5v4.2h4.2"
                stroke="currentColor"
                strokeWidth="1.75"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
              <path
                d="M3 12a9 9 0 0 0 15.36 6.36"
                stroke="currentColor"
                strokeWidth="1.75"
                strokeLinecap="round"
              />
              <path
                d="M18.5 20.5v-4.2h-4.2"
                stroke="currentColor"
                strokeWidth="1.75"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </svg>
          </button>
          <div className="profile-chip">
            <div className="avatar sm">VR</div>
            <div>
              <div className="user-name">Reviewer</div>
              <div className="user-role">Project overview</div>
            </div>
          </div>
        </div>
      </div>
    </header>
  )
}
