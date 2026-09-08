import type { PipelineStage } from '../api/types'

type EmptyProps = {
  onReload?: () => void
  projectName?: string
}

type RunningProps = {
  stages?: PipelineStage[]
  lessons?: number
  standards?: number
  onReload?: () => void
  projectName?: string
}

export function OverviewLoading() {
  return (
    <div className="overview-state overview-loading" aria-busy="true" aria-label="Loading overview">
      <div className="skeleton-page">
        <div className="sk sk-title" />
        <div className="sk sk-banner" />
        <div className="sk-kpi-row">
          <div className="sk sk-kpi" />
          <div className="sk sk-kpi" />
          <div className="sk sk-kpi" />
          <div className="sk sk-kpi" />
        </div>
        <div className="sk sk-row" />
        <div className="sk sk-row" />
      </div>
    </div>
  )
}

export function OverviewEmpty({ onReload, projectName }: EmptyProps) {
  return (
    <section className="overview-hero overview-empty" aria-live="polite">
      <div className="overview-hero-bg" aria-hidden>
        <span className="orb orb-a" />
        <span className="orb orb-b" />
        <span className="orb orb-c" />
        <span className="grid-fade" />
      </div>

      <div className="overview-hero-card enter-up">
        <div className="overview-hero-kicker enter-up" style={{ ['--d' as string]: '40ms' }}>
          Ready when you are
        </div>

        <div className="overview-hero-icon enter-up" style={{ ['--d' as string]: '80ms' }} aria-hidden>
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

        <h2 className="enter-up" style={{ ['--d' as string]: '120ms' }}>
          Upload PDF + XLSX to start
        </h2>
        <p className="enter-up" style={{ ['--d' as string]: '160ms' }}>
          {projectName ? (
            <>
              <strong>{projectName}</strong> has no alignment output yet. Add a PDF and
              XLSX, run the pipeline, and this Overview fills in automatically.
            </>
          ) : (
            <>
              One Overview needs a PDF and an XLSX. When the pipeline finishes, alignments and
              coverage appear here.
            </>
          )}
        </p>

        <div className="overview-flow enter-up" style={{ ['--d' as string]: '200ms' }}>
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

        <div className="overview-hero-actions enter-up" style={{ ['--d' as string]: '280ms' }}>
          {onReload ? (
            <button type="button" className="btn primary" onClick={onReload}>
              Check again
            </button>
          ) : null}
          <span className="overview-hero-note">Outputs stay read-only in Overview</span>
        </div>
      </div>
    </section>
  )
}

export function OverviewRunning({
  stages = [],
  lessons = 0,
  standards = 0,
  onReload,
  projectName,
}: RunningProps) {
  const done = stages.filter((s) => s.status === 'complete' || s.status === 'warning').length
  const total = Math.max(stages.length, 1)
  const pct = Math.round((100 * done) / total)
  const active =
    stages.find((s) => s.status === 'pending') ||
    stages.find((s) => s.status === 'warning') ||
    stages[stages.length - 1]

  return (
    <section className="overview-hero overview-running" aria-live="polite">
      <div className="overview-hero-bg running-bg" aria-hidden>
        <span className="orb orb-a" />
        <span className="orb orb-b" />
        <span className="scan-line" />
      </div>

      <div className="overview-hero-card enter-up">
        <div className="overview-hero-kicker running enter-up" style={{ ['--d' as string]: '40ms' }}>
          <span className="live-dot" aria-hidden />
          In progress
        </div>

        <div className="overview-hero-icon running enter-up" style={{ ['--d' as string]: '80ms' }} aria-hidden>
          <span className="pulse-ring" />
          <span className="pulse-ring delay" />
          <svg className="spin-slow" width="30" height="30" viewBox="0 0 24 24" fill="none">
            <path
              d="M12 3.2a8.8 8.8 0 1 1-7.6 4.4"
              stroke="currentColor"
              strokeWidth="1.7"
              strokeLinecap="round"
            />
            <path d="M4.4 3.6v4.2H8.6" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </div>

        <h2 className="enter-up" style={{ ['--d' as string]: '120ms' }}>
          Pipeline running…
        </h2>
        <p className="enter-up" style={{ ['--d' as string]: '160ms' }}>
          {projectName ? <strong>{projectName}</strong> : 'This project'} is processing. Overview
          metrics unlock when judge results are ready
          {active ? (
            <>
              {' '}
              — currently on <em>{active.name}</em>
            </>
          ) : null}
          .
        </p>

        <div className="run-progress enter-up" style={{ ['--d' as string]: '200ms' }}>
          <div className="run-progress-top">
            <span>Pipeline progress</span>
            <strong>{pct}%</strong>
          </div>
          <div className="run-progress-track" role="progressbar" aria-valuenow={pct} aria-valuemin={0} aria-valuemax={100}>
            <div className="run-progress-fill" style={{ width: `${pct}%` }} />
            <div className="run-progress-sheen" />
          </div>
          <div className="overview-running-meta">
            <span>
              <strong>{lessons}</strong> lessons
            </span>
            <span>
              <strong>{standards}</strong> standards
            </span>
            <span>
              <strong>
                {done}/{total}
              </strong>{' '}
              stages
            </span>
          </div>
        </div>

        {stages.length > 0 ? (
          <ul className="overview-stage-list enter-up" style={{ ['--d' as string]: '240ms' }}>
            {stages.map((s, i) => (
              <li
                key={s.id}
                className={`stage-${s.status}`}
                style={{ ['--i' as string]: i }}
              >
                <span className="stage-dot" aria-hidden />
                <span className="stage-name">{s.name}</span>
                <span className="stage-count">{s.count || s.status}</span>
              </li>
            ))}
          </ul>
        ) : null}

        <div className="overview-hero-actions enter-up" style={{ ['--d' as string]: '300ms' }}>
          {onReload ? (
            <button type="button" className="btn primary" onClick={onReload}>
              Refresh status
            </button>
          ) : null}
          <span className="overview-hero-note">Auto-updates when you refresh</span>
        </div>
      </div>
    </section>
  )
}
