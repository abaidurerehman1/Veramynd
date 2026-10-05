import { ANCHORS } from '../../../config/site'
import AudienceColumns from './AudienceColumns'
import JudgeCard from './JudgeCard'
import './audience.css'

export function AudienceSection() {
  return (
    <section id={ANCHORS.audience} className="ro-section" aria-label="Who it's for">
      <div className="ro-section__bg" aria-hidden="true" />
      <div className="ro-section__grain" aria-hidden="true" />

      <div className="ro-inner">
        <header className="ro-header">
          <p className="ro-label">
            <span className="ro-label__dot" aria-hidden="true" />
            Who it&apos;s for
          </p>
          <h2 className="ro-title">Built for Every Alignment Role.</h2>
          <p className="ro-subtitle">
            Whether you publish, review, or teach to the standards, Veramynd gives{' '}
            <br />
            every alignment decision a paper trail.
          </p>
        </header>

        <AudienceColumns />
        <JudgeCard />
      </div>
    </section>
  )
}

export default AudienceSection
