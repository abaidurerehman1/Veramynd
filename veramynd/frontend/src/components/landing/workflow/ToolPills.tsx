type Props = { label: string; tools: string[] }

export function ToolPills({ label, tools }: Props) {
  return (
    <div className="mi-integrations">
      <p className="mi-integrations__label">{label}</p>
      <ul className="mi-integrations__list">
        {tools.map((name) => (
          <li key={name} className="mi-pill">{name}</li>
        ))}
      </ul>
    </div>
  )
}

export default ToolPills
