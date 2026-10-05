import { useState } from 'react'
import { Link } from 'react-router-dom'
import { ANCHORS } from '../../../config/site'

const LINKS = [
  { label: 'How it works', href: `#${ANCHORS.howItWorks}` },
  { label: 'Pipeline', href: `#${ANCHORS.pipeline}` },
  { label: "Who it's for", href: `#${ANCHORS.audience}` },
  { label: 'Resources', href: `#${ANCHORS.resources}` },
  { label: 'Docs', to: '/docs' },
  { label: 'Sign in', to: '/login' },
]

export function HeroNavigation() {
  const [open, setOpen] = useState(false)

  return (
    <nav className="fs-nav" aria-label="Site navigation" data-open={open}>
      <button
        type="button"
        className="fs-nav__toggle"
        aria-expanded={open}
        aria-controls="fs-nav-list"
        onClick={() => setOpen((v) => !v)}
      >
        Menu
      </button>
      <ul className="fs-nav__list" id="fs-nav-list">
        {LINKS.map((link) => (
          <li key={link.label}>
            {link.to ? (
              <Link to={link.to}>{link.label}</Link>
            ) : (
              <a href={link.href} onClick={() => setOpen(false)}>{link.label}</a>
            )}
          </li>
        ))}
      </ul>
    </nav>
  )
}

export default HeroNavigation
