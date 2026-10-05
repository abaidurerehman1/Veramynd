import { ANCHORS } from '../../../config/site'
import { CornerArcArt, LensArt, TargetArt } from './Illustrations'
import ResourceCard from './ResourceCard'
import './resources.css'

export function ResourcesSection() {
  return (
    <section id={ANCHORS.resources} className="ln-section" aria-label="Resources">
      <div className="ln-inner">
        <div className="ln-header">
          <div>
            <p className="ln-label">
              <span className="ln-label__dot" aria-hidden="true" />
              Resources
            </p>
            <h2 className="ln-title">
              <span>Docs, Results, and Reports,</span>
              <span>All in the Open.</span>
            </h2>
          </div>
          <p className="ln-desc">
            <span>Everything you need to run Veramynd, understand its verdicts,</span>{' '}
            <span>and check the numbers behind them.</span>
          </p>
        </div>

        <div className="ln-row">
          <ResourceCard
            tone="pink"
            title="Documentation"
            lines={['Setup, inputs, pipeline stages, and', 'how to read every verdict.']}
            cta="Read the docs"
            to="/docs"
            art={<CornerArcArt />}
          />
          <ResourceCard
            tone="blue"
            title="Gold-Set Results"
            lines={['Recall and judge accuracy against', 'SME labels, with sample sizes.']}
            cta="See the metrics"
            to="/docs#metrics"
            art={<TargetArt />}
          />
          <ResourceCard
            tone="cyan"
            title="Client Reports"
            lines={['Correlation DOCX and XLSX with', 'parent roll-ups, plus full CSVs.']}
            cta="View export formats"
            to="/docs#report"
            art={<LensArt />}
          />
          <ResourceCard
            tone="tan"
            title="Privacy & Terms"
            lines={['How your curriculum files are handled', 'and the terms for using Veramynd.']}
            cta="Read the policies"
            to="/privacy"
          />
        </div>
      </div>
    </section>
  )
}

export default ResourcesSection
