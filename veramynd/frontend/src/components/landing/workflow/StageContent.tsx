import { Link } from 'react-router-dom'
import ToolPills from './ToolPills'
import type { Stage } from './stages'

export function StageContent({ stage }: { stage: Stage }) {
  return (
    <div className="mi-content">
      <p className="mi-content__label">
        <span className="mi-content__dot" aria-hidden="true" />
        {stage.tab}
      </p>
      <h3 className="mi-content__title">
        {stage.title.map((line) => (
          <span key={line}>{line}</span>
        ))}
      </h3>
      <p className="mi-content__desc">
        {stage.description[0]}{' '}
        <br />
        {stage.description[1]}
      </p>
      <Link to={`/docs#${stage.id}`} className="mi-content__action">
        {stage.linkLabel} <span aria-hidden="true">→</span>
      </Link>
      <ToolPills label={stage.toolsLabel} tools={stage.tools} />
    </div>
  )
}

export default StageContent
