// Headline gold-set results (Batch-1: EL Education G1 Module 2 × Georgia Grade 1 ELA).
type Metric = { label: string; value: string; note: string }

const METRICS: Metric[] = [
  { label: 'Recall@25', value: '100%', note: 'Retrieval recall on 20 SME-labeled positives' },
  { label: 'Judge exact', value: '20/20', note: '3-class match vs SME on four gold lessons' },
  { label: 'vs SME master', value: '93.1%', note: '95 of 102 pairs on the four-lesson overlap' },
  { label: 'Lessons judged', value: '40', note: 'Every lesson in the Batch-1 teacher guide' },
  { label: 'GA ELA standards', value: '188', note: 'Georgia Grade 1 ELA framework, adopted 2023' },
  { label: 'Binary precision', value: '100%', note: 'Full-or-partial vs none, on the four gold lessons' },
]

export function MetricsTicker() {
  return (
    <div className="fs-ticker" role="region" aria-label="Gold-set results">
      <ul className="fs-ticker__list">
        {METRICS.map((m) => (
          <li className="fs-ticker__item" key={m.label} title={m.note}>
            <span>{m.label}</span>
            <span>
              <span aria-hidden="true">↗</span> {m.value}
            </span>
          </li>
        ))}
      </ul>
    </div>
  )
}

export default MetricsTicker
