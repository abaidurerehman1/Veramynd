import CodeContent from './CodeContent'
import type { CodeLine } from './commands'

function WindowControls() {
  return (
    <span className="ch-term__controls" aria-hidden="true">
      <span className="ch-term__dot ch-term__dot--red" />
      <span className="ch-term__dot ch-term__dot--yellow" />
      <span className="ch-term__dot ch-term__dot--green" />
    </span>
  )
}

export type TerminalWindowProps = {
  title: string
  lines: CodeLine[]
}

export function TerminalWindow({ title, lines }: TerminalWindowProps) {
  return (
    <div className="ch-term">
      <div className="ch-term__header">
        <p className="ch-term__title">{title}</p>
        <WindowControls />
      </div>
      <div className="ch-term__body">
        <CodeContent lines={lines} label={`${title}: command-line example`} />
      </div>
    </div>
  )
}

export default TerminalWindow
