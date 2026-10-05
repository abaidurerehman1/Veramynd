import { Link } from 'react-router-dom'
import SparkleMark from './SparkleMark'

const POINTS = ['Full, partial, or none for every pair', 'Clause-by-clause reasoning', 'Ungrounded quotes rejected']

export function JudgeCard() {
  return (
    <div className="ro-card">
      <div className="ro-card__visual" aria-hidden="true">
        <span className="ro-card__ring ro-card__ring--outer" />
        <span className="ro-card__ring ro-card__ring--inner" />
        <span className="ro-card__core">
          <SparkleMark />
        </span>
      </div>

      <div className="ro-card__panel">
        <svg className="ro-card__lines" viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true">
          <line x1="73.33" y1="0" x2="63.91" y2="100" />
          <line x1="84.6" y1="0" x2="74.94" y2="100" />
        </svg>
        <div className="ro-card__grain" aria-hidden="true" />

        <div className="ro-card__content">
          <p className="ro-card__label">
            <span className="ro-card__dot" aria-hidden="true" />
            Alignment Judge
          </p>
          <h3 className="ro-card__title">
            <span>AI Judgment With</span>
            <span>a Paper Trail.</span>
          </h3>
          <p className="ro-card__sub">Every verdict cites the lesson text that earned it.</p>
          <ul className="ro-card__points">
            {POINTS.map((point) => (
              <li key={point}>
                <span aria-hidden="true">→</span>
                {point}
              </li>
            ))}
          </ul>
          <Link to="/docs#judge" className="ro-card__cta">
            See how it judges <span aria-hidden="true">→</span>
          </Link>
        </div>
      </div>
    </div>
  )
}

export default JudgeCard
