import { useMemo } from 'react'
import type { LessonCoverageRow, OverviewMetrics, ReviewItem } from '../../api/types'
import { lessonMeta } from '../../lib/format'
import type { PipelineJob } from '../LivePipelineProgress'
import ActivityPhone from './ActivityPhone'
import { CitedBadge, FullBadge, PartialBadge, ReviewBadge } from './icons'
import MetricCard from './MetricCard'
import TrendCard, { type TrendPoint } from './TrendCard'
import './overview-dashboard.css'

type Props = {
  projectId: string
  overview: OverviewMetrics
  coverage: LessonCoverageRow[]
  reviewRows: ReviewItem[]
  jobs: PipelineJob[]
}

const pct = (part: number, whole: number) => (whole > 0 ? (100 * part) / whole : 0)
const fmt = (n: number) => `${Math.round(n * 10) / 10}%`

export function OverviewDashboard({ projectId, overview, coverage, reviewRows, jobs }: Props) {
  const points: TrendPoint[] = useMemo(
    () =>
      coverage
        .map((row) => ({ row, meta: lessonMeta(row.resource_id) }))
        .sort((a, b) => a.meta.unit - b.meta.unit || a.meta.lesson - b.meta.lesson)
        .map(({ row, meta }) => ({ label: meta.short, unit: meta.unit, value: row.aligned || 0 })),
    [coverage],
  )

  const total = overview.alignments
  const full = overview.by_status.full || 0
  const partial = overview.by_status.partial || 0
  const positive = full + partial
  const review = overview.review_required || 0
  const aligned = points.reduce((s, p) => s + p.value, 0)

  return (
    <div className="vd">
      <div className="vd-grid">
        <ActivityPhone projectId={projectId} jobs={jobs} reviewRows={reviewRows} />

        <div className="vd-right">
          <TrendCard
            title="Alignment Trends"
            total={aligned}
            percent={Math.round(overview.alignment_coverage_pct)}
            percentLabel="Standards coverage across the framework"
            points={points}
          />

          <div className="vd-metrics">
            <MetricCard
              title="Full Alignments"
              icon={<FullBadge />}
              value={full}
              chip={fmt(pct(full, total))}
              chipTone="up"
              chipLabel="Share of all judged pairs"
              sub="All clauses met"
              percent={pct(full, positive)}
              percentLabel="Share of positive verdicts that are full"
            />
            <MetricCard
              title="Partial Alignments"
              icon={<PartialBadge />}
              value={partial}
              chip={fmt(pct(partial, total))}
              chipTone="warn"
              chipLabel="Share of all judged pairs"
              sub="Some clauses met"
              percent={pct(partial, positive)}
              percentLabel="Share of positive verdicts that are partial"
            />
            <MetricCard
              title="Review Queue"
              icon={<ReviewBadge />}
              value={review}
              chip={fmt(pct(review, total))}
              chipTone="down"
              chipLabel="Share of judged pairs that need a human check"
              sub={`${overview.escalated} escalated to Opus`}
              percent={pct(total - review, total)}
              percentLabel="Judged pairs that need no human check"
            />
            <MetricCard
              title="Standards Cited"
              icon={<CitedBadge />}
              value={overview.positive_standards_cited}
              chip={fmt(overview.alignment_coverage_pct)}
              chipTone="up"
              chipLabel="Standards coverage across the framework"
              sub={`of ${overview.standards_leaves.toLocaleString()} leaf standards`}
              percent={pct(overview.grounded, total)}
              percentLabel="Judged pairs whose evidence is grounded in the source"
            />
          </div>
        </div>
      </div>
    </div>
  )
}

export default OverviewDashboard
