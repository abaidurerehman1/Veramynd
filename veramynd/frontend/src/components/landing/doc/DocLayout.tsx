import type { ReactNode } from 'react'
import { Link, NavLink } from 'react-router-dom'
import FooterLogo from '../footer/FooterLogo'
import SiteFooter from '../footer/SiteFooter'
import { SITE } from '../../../config/site'
import useDocumentTitle from '../useDocumentTitle'
import useHashScroll from '../useHashScroll'
import './doc.css'

export type TocItem = { id: string; label: string }

type Props = {
  eyebrow: string
  title: string
  intro: ReactNode
  meta?: string
  toc: TocItem[]
  /** Extra controls rendered under the intro (e.g. docs search). */
  tools?: ReactNode
  children: ReactNode
}

const NAV = [
  { to: '/docs', label: 'Docs' },
  { to: '/privacy', label: 'Privacy' },
  { to: '/terms', label: 'Terms' },
]

/** Shared shell for the public Docs, Privacy and Terms pages. */
export function DocLayout({ eyebrow, title, intro, meta, toc, tools, children }: Props) {
  useHashScroll()
  useDocumentTitle(`${title} · ${SITE.name}`)

  return (
    <div className="doc-page">
      <header className="doc-header">
        <div className="doc-header__inner">
          <FooterLogo />
          <nav className="doc-header__nav" aria-label="Public pages">
            <Link to="/landing">Product</Link>
            {NAV.map((item) => (
              <NavLink key={item.to} to={item.to}>
                {item.label}
              </NavLink>
            ))}
            <Link to="/login" className="doc-header__signin">
              Sign in
            </Link>
          </nav>
        </div>
      </header>

      <main className="doc-main">
        <div className="doc-hero">
          <p className="doc-eyebrow">
            <span aria-hidden="true" />
            {eyebrow}
          </p>
          <h1 className="doc-title">{title}</h1>
          <div className="doc-intro">{intro}</div>
          {meta && <p className="doc-meta">{meta}</p>}
          {tools}
        </div>

        <div className="doc-body">
          <nav className="doc-toc" aria-label="On this page">
            <p className="doc-toc__label">On this page</p>
            <ol>
              {toc.map((item) => (
                <li key={item.id}>
                  <a href={`#${item.id}`}>{item.label}</a>
                </li>
              ))}
            </ol>
          </nav>
          <article className="doc-content">{children}</article>
        </div>
      </main>

      <SiteFooter />
    </div>
  )
}

/** A titled, anchor-linkable section inside a doc page. */
export function DocSection({ id, title, children }: { id: string; title: string; children: ReactNode }) {
  return (
    <section id={id} className="doc-section" data-doc-section>
      <h2>
        <a href={`#${id}`} className="doc-section__anchor" aria-hidden="true" tabIndex={-1}>
          #
        </a>
        {title}
      </h2>
      {children}
    </section>
  )
}

export default DocLayout
