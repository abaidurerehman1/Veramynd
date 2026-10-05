import { ProjectSwitcher } from './ProjectSwitcher'
import { SidebarToggleIcon } from './SidebarToggleIcon'

type Props = {
  crumbs: string
  showMenu: boolean
  onToggle: () => void
  onReload?: () => void | Promise<void>
  /** Where a page can render its own crumbs and controls (see TopbarContent). */
  slotRef?: (el: HTMLElement | null) => void
  claimed?: boolean
}

export function Topbar({ crumbs, showMenu, onToggle, onReload, slotRef, claimed = false }: Props) {
  // "Veramynd / Project / Section": the last part is the current page.
  const parts = crumbs.split(' / ').filter(Boolean)
  const here = parts.pop() ?? ''

  return (
    <header className={`app-header${claimed ? ' has-slot' : ''}`} role="banner">
      <div className="app-header-inner">
        <div className="greet">
          {showMenu && (
            <button type="button" className="menu-btn top-menu" onClick={onToggle} aria-label="Toggle sidebar" title="Toggle sidebar">
              <SidebarToggleIcon />
            </button>
          )}
          {claimed ? null : (
          <nav className="greet-copy app-crumbs" aria-label="Breadcrumb">
            {parts.map((p) => (
              <span key={p} className="app-crumb">
                {p}
                <span className="app-crumb-sep" aria-hidden="true">
                  /
                </span>
              </span>
            ))}
            <span className="app-crumb here" aria-current="page">
              {here}
            </span>
          </nav>
          )}
        </div>
        <div className="topbar-slot" ref={slotRef} />
        {claimed ? null : (
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
        )}
      </div>
    </header>
  )
}
