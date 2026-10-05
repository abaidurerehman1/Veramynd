import type { CodeLine } from './commands'

export type CodeContentProps = {
  lines: CodeLine[]
  label: string
}

export function CodeContent({ lines, label }: CodeContentProps) {
  return (
    <pre className="ch-code" aria-label={label}>
      <code>
        {lines.map((line, i) =>
          line ? (
            <span key={i} className="ch-code__line" style={{ paddingLeft: line.indent }}>
              {line.tokens.map(([kind, text], j) => (
                <span key={j} className={`ch-tok-${kind}`}>{text}</span>
              ))}
            </span>
          ) : (
            <span key={i} className="ch-code__blank" />
          ),
        )}
      </code>
    </pre>
  )
}

export default CodeContent
