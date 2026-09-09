import { Link } from 'react-router-dom'
import { NONE_PROJECT_ID } from '../project/ProjectContext'

export const INGEST_PATH = `/projects/${NONE_PROJECT_ID}/ingestion`

export function NoProjectPage() {
  return (
    <div className="analytics analytics-state">
      <section className="overview-hero overview-empty" aria-live="polite">
        <div className="overview-hero-bg" aria-hidden>
          <span className="orb orb-a" />
          <span className="orb orb-b" />
          <span className="orb orb-c" />
          <span className="grid-fade" />
        </div>

        <div className="overview-hero-card enter-up none-project-card">
          <div className="overview-hero-kicker">Ready when you are</div>

          <div className="overview-hero-icon" aria-hidden>
            <span className="icon-glow" />
            <svg width="32" height="32" viewBox="0 0 24 24" fill="none">
              <path
                d="M8 3.75h6.2L18.5 8v11.25a1.5 1.5 0 0 1-1.5 1.5H8a1.5 1.5 0 0 1-1.5-1.5V5.25A1.5 1.5 0 0 1 8 3.75Z"
                stroke="currentColor"
                strokeWidth="1.5"
              />
              <path d="M14.2 3.75V8H18.5" stroke="currentColor" strokeWidth="1.5" />
              <path d="M9.5 12.5h5M9.5 15.5h3.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
              <circle cx="17.2" cy="15.8" r="3.2" fill="var(--green-soft)" stroke="currentColor" strokeWidth="1.4" />
              <path d="M17.2 14.4v2.8M15.8 15.8h2.8" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" />
            </svg>
          </div>

          <h2>Upload PDF + XLSX to start</h2>
          <p>
            No project selected. Go to Ingestion to upload a new PDF and XLSX. The upload appears in
            the project switcher immediately but stays idle — you must explicitly start Complete
            auto or step-by-step (with confirmation). Overview then updates empty → in progress →
            ready.
          </p>

          <div className="overview-flow">
            {[
              { n: '01', t: 'PDF', d: 'Curriculum source' },
              { n: '02', t: 'XLSX', d: 'Standards file' },
              { n: '03', t: 'Pipeline run', d: 'Parse → judge → Overview' },
            ].map((step, i) => (
              <div key={step.n} className="overview-flow-step" style={{ ['--i' as string]: i }}>
                <div className="ofs-num">{step.n}</div>
                <div className="ofs-copy">
                  <strong>{step.t}</strong>
                  <span>{step.d}</span>
                </div>
                {i < 2 ? <div className="ofs-join" aria-hidden /> : null}
              </div>
            ))}
          </div>

          <div className="none-actions overview-hero-actions">
            <Link className="btn primary" to={INGEST_PATH}>
              Go to Ingestion
            </Link>
          </div>
        </div>
      </section>
    </div>
  )
}
