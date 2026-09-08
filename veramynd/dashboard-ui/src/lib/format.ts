export function fmtPct(v: number | null | undefined): string {
  if (v == null || v === ('' as unknown as number)) return '—'
  const n = Number(v)
  if (Number.isNaN(n)) return '—'
  const pct = n <= 1 ? n * 100 : n
  return `${Math.round(pct)}%`
}

export function lessonMeta(rid: string) {
  const m = String(rid || '').match(/U(\d+)L(\d+)/i)
  if (!m) {
    return {
      unit: 0,
      lesson: 0,
      short: String(rid || '').replace(/^G1M2/i, '') || '—',
    }
  }
  return {
    unit: Number(m[1]),
    lesson: Number(m[2]),
    short: `U${m[1]}L${m[2]}`,
  }
}

export function greeting(): string {
  return 'Welcome'
}

/** Formats ISO date as "Last reviewed Mar 14" (includes year if not current). */
export function lastReviewedLabel(iso: string | null | undefined): string | null {
  if (!iso) return null
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return null
  const sameYear = d.getFullYear() === new Date().getFullYear()
  const month = d.toLocaleString('en-US', { month: 'short' })
  const day = d.getDate()
  if (sameYear) return `Last reviewed ${month} ${day}`
  return `Last reviewed ${month} ${day}, ${d.getFullYear()}`
}
