import { useEffect } from 'react'
import { useLocation } from 'react-router-dom'

/**
 * Scroll to the element named by the URL hash after client-side navigation
 * (React Router does not do this on its own), or to the top when there is none.
 */
export function useHashScroll() {
  const { hash, pathname } = useLocation()

  useEffect(() => {
    if (!hash) {
      window.scrollTo(0, 0)
      return
    }
    const id = decodeURIComponent(hash.slice(1))
    // Wait a frame so the target section has rendered.
    const frame = requestAnimationFrame(() => {
      document.getElementById(id)?.scrollIntoView({ behavior: 'smooth', block: 'start' })
    })
    return () => cancelAnimationFrame(frame)
  }, [hash, pathname])
}

export default useHashScroll
