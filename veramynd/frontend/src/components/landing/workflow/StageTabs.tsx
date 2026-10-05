import type { Stage } from './stages'

type Props = {
  stages: Stage[]
  active: Stage['id']
  onChange: (id: Stage['id']) => void
}

export function StageTabs({ stages, active, onChange }: Props) {
  return (
    <div className="mi-tabs" role="tablist" aria-label="Pipeline stages">
      {stages.map((stage) => (
        <button
          key={stage.id}
          type="button"
          role="tab"
          id={`stage-tab-${stage.id}`}
          aria-selected={stage.id === active}
          aria-controls="stage-panel"
          className="mi-tabs__tab"
          onClick={() => onChange(stage.id)}
        >
          {stage.tab}
        </button>
      ))}
    </div>
  )
}

export default StageTabs
