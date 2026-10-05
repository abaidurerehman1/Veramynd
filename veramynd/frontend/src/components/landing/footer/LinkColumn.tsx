import { Link } from 'react-router-dom'

export type FooterLink = { label: string; to: string }

type Props = {
  heading: string
  links: FooterLink[]
}

/** Internal routes use the router; mailto and external links use a plain anchor. */
export function FooterAnchor({ label, to }: FooterLink) {
  return to.startsWith('/') ? <Link to={to}>{label}</Link> : <a href={to}>{label}</a>
}

export function LinkColumn({ heading, links }: Props) {
  return (
    <nav className="cf-col" aria-label={heading}>
      <h3 className="cf-col__heading">{heading}</h3>
      <ul className="cf-col__list">
        {links.map((link) => (
          <li key={link.label}>
            <FooterAnchor {...link} />
          </li>
        ))}
      </ul>
    </nav>
  )
}

export default LinkColumn
