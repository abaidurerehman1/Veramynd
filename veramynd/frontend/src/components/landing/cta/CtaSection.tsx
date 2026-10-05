import { Link } from 'react-router-dom'
import './cta.css'

export function CtaSection() {
  return (
    <section className="cf-section" aria-label="Get started">
      <div className="cf-inner">
        <div className="cf-cta">
          <div className="cf-cta__grain" aria-hidden="true" />
          <h2 className="cf-cta__title">
            <span>Align smarter, let</span>
            <span>evidence lead the way.</span>
          </h2>
          <p className="cf-cta__text">
            <span>Hand alignment is slow, expensive, and inconsistent between raters. Veramynd applies one</span>{' '}
            <span>rubric identically across every lesson and standard, with evidence pulled straight from</span>{' '}
            <span>the source document.</span>
          </p>
          <Link to="/signup" className="cf-cta__button">Get Started</Link>
        </div>
      </div>
    </section>
  )
}

export default CtaSection
