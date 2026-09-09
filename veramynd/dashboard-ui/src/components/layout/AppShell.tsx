import { useEffect, useState } from 'react'
import { Outlet } from 'react-router-dom'
import { Sidebar } from './Sidebar'
import { Topbar } from './Topbar'

type Props = {
  crumbs: string
  onReload?: () => void | Promise<void>
}

const MOBILE_MQ = '(max-width: 900px)'

export function AppShell({ crumbs, onReload }: Props) {
  const [collapsed, setCollapsed] = useState(() => window.matchMedia(MOBILE_MQ).matches)
  const [isMobile, setIsMobile] = useState(() => window.matchMedia(MOBILE_MQ).matches)

  useEffect(() => {
    const mq = window.matchMedia(MOBILE_MQ)
    const onChange = () => {
      const mobile = mq.matches
      setIsMobile(mobile)
      setCollapsed(mobile)
    }
    mq.addEventListener('change', onChange)
    return () => mq.removeEventListener('change', onChange)
  }, [])

  const toggle = () => setCollapsed((v) => !v)
  const closeNav = () => {
    if (isMobile) setCollapsed(true)
  }

  return (
    <div className={`app${collapsed ? ' nav-collapsed' : ''}${isMobile ? ' is-mobile' : ''}`}>
      {isMobile && !collapsed ? (
        <button type="button" className="nav-backdrop" aria-label="Close navigation" onClick={closeNav} />
      ) : null}
      <Sidebar collapsed={collapsed} onToggle={toggle} />
      <div className="main">
        <Topbar crumbs={crumbs} showMenu={collapsed || isMobile} onToggle={toggle} onReload={onReload} />
        <main className="page">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
