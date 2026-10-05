import { useState } from 'react'
import { ANCHORS } from '../../../config/site'
import { COMMAND_TABS, type CommandTab } from './commands'
import TerminalWindow from './TerminalWindow'
import './engine.css'

export function EngineSection() {
  const [active, setActive] = useState<CommandTab['id']>('verify')
  const tab = COMMAND_TABS.find((t) => t.id === active) ?? COMMAND_TABS[0]

  return (
    <section id={ANCHORS.pipeline} className="ch-section" aria-label="The pipeline">
      <div className="ch-section__bg" aria-hidden="true" />
      <div className="ch-section__grain" aria-hidden="true" />

      <div className="ch-inner">
        <div className="ch-header">
          <div className="ch-header__lead">
            <p className="ch-label">
              <span className="ch-label__dot" aria-hidden="true" />
              The engine
            </p>
            <h2 className="ch-title">
              <span>Run It From the CLI</span>
              <span>or the Operator UI.</span>
            </h2>
          </div>
          <p className="ch-desc">
            The same pipeline runs from the veramynd-parser CLI or the{' '}
            <br />
            operator UI, step by step or end to end, resumable after any{' '}
            <br />
            interruption, with every artifact saved to disk.
          </p>
        </div>

        <div className="ch-tabs" role="tablist" aria-label="Pipeline commands">
          {COMMAND_TABS.map((t) => (
            <button
              key={t.id}
              type="button"
              role="tab"
              id={`cmd-tab-${t.id}`}
              aria-selected={t.id === active}
              aria-controls="cmd-panel"
              className="ch-tabs__tab"
              onClick={() => setActive(t.id)}
            >
              {t.tab}
            </button>
          ))}
        </div>

        <div role="tabpanel" id="cmd-panel" aria-labelledby={`cmd-tab-${tab.id}`}>
          <TerminalWindow title={tab.title} lines={tab.lines} />
        </div>
      </div>
    </section>
  )
}

export default EngineSection
