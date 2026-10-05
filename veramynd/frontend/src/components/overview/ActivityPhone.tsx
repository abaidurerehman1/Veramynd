import { useMemo, useState } from 'react'
import { Link, NavLink } from 'react-router-dom'
import type { ReviewItem } from '../../api/types'
import { lessonMeta } from '../../lib/format'
import type { PipelineJob } from '../LivePipelineProgress'
import {
  CalendarIcon,
  ChatIcon,
  ChevronDownIcon,
  GaugeIcon,
  HomeIcon,
  PeopleIcon,
  PlusIcon,
  SearchIcon,
  StatusGlyph,
} from './icons'

type Props = {
  projectId: string
  jobs: PipelineJob[]
  reviewRows: ReviewItem[]
}

type DayActivity = { total: number; completed: number; failed: number; full: number }

const WEEKDAYS = ['M', 'T', 'W', 'T', 'F', 'S', 'S']

function dayKey(d: Date) {
  return `${d.getFullYear()}-${d.getMonth()}-${d.getDate()}`
}

function isFailed(status: string) {
  return /fail|error|cancel/i.test(status || '')
}

function isComplete(status: string) {
  return /complete|success|done|finished/i.test(status || '')
}

/** Pipeline jobs grouped by calendar day. */
function useActivityByDay(jobs: PipelineJob[]) {
  return useMemo(() => {
    const map = new Map<string, DayActivity>()
    jobs.forEach((job) => {
      const d = new Date(job.created_at)
      if (Number.isNaN(d.getTime())) return
      const key = dayKey(d)
      const entry = map.get(key) ?? { total: 0, completed: 0, failed: 0, full: 0 }
      entry.total += 1
      if (isComplete(job.status)) entry.completed += 1
      if (isFailed(job.status)) entry.failed += 1
      if (job.mode === 'full') entry.full += 1
      map.set(key, entry)
    })
    return map
  }, [jobs])
}

/** Monday-first grid of the month: leading blanks, then each day. */
function monthCells(month: Date) {
  const first = new Date(month.getFullYear(), month.getMonth(), 1)
  const days = new Date(month.getFullYear(), month.getMonth() + 1, 0).getDate()
  const lead = (first.getDay() + 6) % 7
  return [
    ...Array.from({ length: lead }, () => null),
    ...Array.from({ length: days }, (_, i) => new Date(month.getFullYear(), month.getMonth(), i + 1)),
  ]
}

function dayTitle(date: Date, a?: DayActivity) {
  const label = date.toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
  if (!a) return label
  const parts = [`${a.total} pipeline job${a.total === 1 ? '' : 's'}`]
  if (a.completed) parts.push(`${a.completed} completed`)
  if (a.failed) parts.push(`${a.failed} failed`)
  return `${label}: ${parts.join(', ')}`
}

function capitalize(text: string) {
  return text ? text[0].toUpperCase() + text.slice(1) : text
}

function reviewStatus(row: ReviewItem): 'full' | 'partial' | 'none' | 'escalated' {
  if (row.escalated) return 'escalated'
  return row.matched_status
}

export function ActivityPhone({ projectId, jobs, reviewRows }: Props) {
  const today = new Date()
  const [offset, setOffset] = useState(0) // 0 = this month, -1 = last month
  const month = new Date(today.getFullYear(), today.getMonth() + offset, 1)
  const activity = useActivityByDay(jobs)
  const cells = monthCells(month)
  const base = `/projects/${projectId}`
  const items = reviewRows.slice(0, 3)

  return (
    <section className="vd-card vd-phone-panel" aria-label="Pipeline activity and review queue">
      <div className="vd-phone">
        <div className="vd-phone__screen">
        <header className="vd-phone__head">
          <h2>Activity</h2>
          <div className="vd-phone__actions">
            <Link to={`${base}/alignment`} className="vd-round-btn" aria-label="Search alignments">
              <SearchIcon />
            </Link>
            <Link to={`${base}/ingestion`} className="vd-round-btn" aria-label="New upload">
              <PlusIcon />
            </Link>
          </div>
        </header>

        <div className="vd-cal">
          <div className="vd-cal__top">
            <span>{month.toLocaleDateString(undefined, { month: 'long', year: 'numeric' })}</span>
            <label className="vd-cal__range">
              <select value={offset} onChange={(e) => setOffset(Number(e.target.value))} aria-label="Month">
                <option value={0}>This Month</option>
                <option value={-1}>Last Month</option>
              </select>
              <span aria-hidden="true">{offset === 0 ? 'This Month' : 'Last Month'}</span>
              <ChevronDownIcon />
            </label>
          </div>
          <div className="vd-cal__grid" role="grid" aria-label="Pipeline jobs by day">
            {WEEKDAYS.map((d, i) => (
              <span key={`h${i}`} className="vd-cal__dow" role="columnheader">
                {d}
              </span>
            ))}
            {cells.map((date, i) => {
              if (!date) return <span key={`b${i}`} className="vd-cal__blank" />
              const a = activity.get(dayKey(date))
              const isToday = dayKey(date) === dayKey(today)
              const cls = ['vd-day', isToday ? 'today' : '', a?.full ? 'run' : ''].join(' ').trim()
              return (
                <span key={dayKey(date)} className={cls} role="gridcell" title={dayTitle(date, a)}>
                  {date.getDate()}
                  {a && !a.full && (a.failed || a.completed) ? (
                    <i className={a.failed ? 'dot red' : 'dot green'} aria-hidden="true" />
                  ) : null}
                </span>
              )
            })}
          </div>
        </div>

        <div className="vd-today">
          <h3>Review</h3>
          <Link to={`${base}/review`}>
            {reviewRows.length} {reviewRows.length === 1 ? 'Item' : 'Items'}
          </Link>
        </div>

        <ul className="vd-tasks">
          {items.length === 0 ? (
            <li className="vd-task vd-task--empty">
              <span className="vd-task__icon">
                <StatusGlyph status="full" />
              </span>
              <div className="vd-task__text">
                <strong>Nothing to review</strong>
                <span>All verdicts cleared</span>
              </div>
            </li>
          ) : (
            items.map((row) => {
              const meta = lessonMeta(row.resource_id)
              return (
                <li key={row.id} className="vd-task" title={row.review_reason}>
                  <span className="vd-task__icon">
                    <StatusGlyph status={reviewStatus(row)} />
                  </span>
                  <div className="vd-task__text">
                    <strong>{row.standard_code}</strong>
                    <span>
                      <span className="vd-task__chips" aria-hidden="true">
                        <i>U{meta.unit || '–'}</i>
                        <i>L{meta.lesson || '–'}</i>
                      </span>
                      {row.review_reason || row.lesson_title}
                    </span>
                  </div>
                  <span className="vd-task__pill">
                    {row.evidence_page ? `p. ${row.evidence_page}` : capitalize(row.confidence || row.matched_status)}
                  </span>
                </li>
              )
            })
          )}
        </ul>
        </div>

        <nav className="vd-tabbar" aria-label="Project pages">
          <NavLink to={base} end aria-label="Overview">
            <HomeIcon />
          </NavLink>
          <NavLink to={`${base}/pipeline`} aria-label="Pipeline">
            <GaugeIcon />
          </NavLink>
          <NavLink to={`${base}/review`} aria-label="Review queue">
            <PeopleIcon />
          </NavLink>
          <span className="vd-tabbar__active">
            <CalendarIcon />
            Activity
          </span>
          <NavLink to={`${base}/logging`} aria-label="Logging">
            <ChatIcon />
          </NavLink>
          <i className="vd-tabbar__home" aria-hidden="true" />
        </nav>
      </div>
    </section>
  )
}

export default ActivityPhone
