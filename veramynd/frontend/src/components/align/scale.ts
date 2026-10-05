// Coverage colour scale and small formatting helpers for the alignment views.

/** Six-step landing cyan-to-blue scale for state coverage. */
export const COV_COLORS = ['var(--cov-0)', 'var(--cov-1)', 'var(--cov-2)', 'var(--cov-3)', 'var(--cov-4)', 'var(--cov-5)']
export const COV_TICKS = ['<20%', '60%', '90%+']

export function band(cov: number) {
  if (cov >= 90) return 5
  if (cov >= 75) return 4
  if (cov >= 60) return 3
  if (cov >= 40) return 2
  if (cov >= 20) return 1
  return 0
}

export function formatDecisionDate(iso: string | null) {
  if (!iso) return ''
  const d = new Date(iso)
  return Number.isNaN(d.getTime()) ? '' : d.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' })
}

