import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'

type Props = {
  tone: 'pink' | 'blue' | 'cyan' | 'tan'
  title: string
  lines: [string, string]
  cta: string
  to: string
  art?: ReactNode
}

export function ResourceCard({ tone, title, lines, cta, to, art }: Props) {
  return (
    <article className={`ln-card ln-card--${tone}`}>
      <div className="ln-card__grain" aria-hidden="true" />
      {art}
      <h3 className="ln-card__title">{title}</h3>
      <p className="ln-card__desc">
        <span>{lines[0]}</span>
        <span>{lines[1]}</span>
      </p>
      <Link to={to} className="ln-card__cta">
        {cta} <span aria-hidden="true">→</span>
      </Link>
    </article>
  )
}

export default ResourceCard
