import { useContext, useEffect, type ReactNode } from 'react'
import { createPortal } from 'react-dom'
import { TopbarSlotContext } from './topbarSlotContext'

/**
 * Lets a page own the app topbar (crumbs on the left, controls on the right), as the Align screens do.
 * While mounted, the topbar's default breadcrumb and actions are hidden.
 */
export function TopbarContent({ children }: { children: ReactNode }) {
  const { target, setClaimed } = useContext(TopbarSlotContext)
  useEffect(() => {
    setClaimed(true)
    return () => setClaimed(false)
  }, [setClaimed])
  return target ? createPortal(children, target) : null
}
