type Props = {
  title: string
  status: string
  description: string
}

export function WorkflowCard({ title, status, description }: Props) {
  return (
    <li className="mi-card">
      <div className="mi-card__head">
        <span className="mi-card__title">{title}</span>
        <span className="mi-card__status">{status}</span>
      </div>
      <p className="mi-card__desc">{description}</p>
    </li>
  )
}

export default WorkflowCard
