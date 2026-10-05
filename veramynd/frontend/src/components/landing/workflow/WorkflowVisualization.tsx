import WorkflowCard from './WorkflowCard'
import type { Stage } from './stages'

// Timeline: completed (black dot + dark rail), in progress (grey dot + pale rail), pending (ring).
function Timeline() {
  return (
    <svg className="mi-timeline" width="9" height="192" viewBox="0 0 9 192" aria-hidden="true">
      <circle cx="4.5" cy="4.5" r="3.5" fill="#000" />
      <line x1="4.5" y1="14" x2="4.5" y2="86" stroke="#222" strokeWidth="1.2" />
      <circle cx="4.5" cy="96.5" r="3.5" fill="#e3e3e3" />
      <line x1="4.5" y1="105" x2="4.5" y2="178" stroke="#e8e8e8" strokeWidth="1.2" />
      <circle cx="4.5" cy="187.5" r="3" fill="none" stroke="#e2e2e2" strokeWidth="1" />
    </svg>
  )
}

export function WorkflowVisualization({ stage }: { stage: Stage }) {
  return (
    <div className="mi-panel" aria-label={`${stage.tab} steps`}>
      <div className="mi-workflow">
        <Timeline />
        <ol className="mi-workflow__cards">
          {stage.steps.map((step) => (
            <WorkflowCard key={step.title} {...step} />
          ))}
        </ol>
      </div>
    </div>
  )
}

export default WorkflowVisualization
