import { useState } from 'react'
import { ANCHORS } from '../../../config/site'
import SectionHeader from './SectionHeader'
import StageContent from './StageContent'
import StageTabs from './StageTabs'
import { STAGES, type Stage } from './stages'
import WorkflowVisualization from './WorkflowVisualization'
import './workflow.css'

export function WorkflowSection() {
  const [active, setActive] = useState<Stage['id']>('parse')
  const stage = STAGES.find((s) => s.id === active) ?? STAGES[0]

  return (
    <section id={ANCHORS.howItWorks} className="mi-section" aria-label="How it works">
      <div className="mi-section__bg" aria-hidden="true" />
      <div className="mi-section__grain" aria-hidden="true" />

      <SectionHeader />
      <StageTabs stages={STAGES} active={active} onChange={setActive} />

      <div className="mi-body" role="tabpanel" id="stage-panel" aria-labelledby={`stage-tab-${stage.id}`}>
        <StageContent stage={stage} />
        <WorkflowVisualization stage={stage} />
      </div>
    </section>
  )
}

export default WorkflowSection
