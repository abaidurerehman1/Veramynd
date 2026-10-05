import { Link } from 'react-router-dom'
import { ANCHORS, SITE, appRoute } from '../../../config/site'
import FooterLogo from './FooterLogo'
import GiantWordmark from './GiantWordmark'
import LinkColumn, { type FooterLink } from './LinkColumn'
import './footer.css'

const COLUMNS: { heading: string; links: FooterLink[] }[] = [
  {
    heading: 'Product',
    links: [
      { label: 'How it works', to: `/landing#${ANCHORS.howItWorks}` },
      { label: 'Pipeline', to: `/landing#${ANCHORS.pipeline}` },
      { label: "Who it's for", to: `/landing#${ANCHORS.audience}` },
      { label: 'Resources', to: `/landing#${ANCHORS.resources}` },
    ],
  },
  {
    heading: 'Workspace',
    links: [
      { label: 'Overview', to: appRoute() },
      { label: 'Ingestion', to: appRoute('ingestion') },
      { label: 'Alignments', to: appRoute('alignment') },
      { label: 'Review queue', to: appRoute('review') },
      { label: 'Exports', to: appRoute('exports') },
    ],
  },
  {
    heading: 'Resources',
    links: [
      { label: 'Documentation', to: '/docs' },
      { label: 'Quick start', to: '/docs#quick-start' },
      { label: 'Gold-set metrics', to: '/docs#metrics' },
      { label: 'CLI reference', to: '/docs#cli' },
      { label: 'Contact', to: `mailto:${SITE.contactEmail}` },
    ],
  },
]

export function SiteFooter() {
  return (
    <div className="cf-site-footer">
      <hr className="cf-divider" />
      <footer className="cf-inner cf-footer">
        <div className="cf-footer__brand">
          <FooterLogo />
          <nav className="cf-legal" aria-label="Legal">
            <Link to="/privacy">Privacy Policy</Link>
            <Link to="/terms">Terms of Use</Link>
          </nav>
        </div>
        {COLUMNS.map((col) => (
          <LinkColumn key={col.heading} {...col} />
        ))}
        <GiantWordmark />
      </footer>
    </div>
  )
}

export default SiteFooter
