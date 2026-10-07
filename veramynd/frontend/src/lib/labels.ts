// Readable labels for internal IDs, so people see names and dates instead of codes.
// The raw ID stays available (e.g. in a tooltip) for support.

/** Run IDs look like 20261006T091853Z-5f24ad5b; upload IDs end in a date like -20261005. */
function dateFromId(id: string): Date | null {
  const run = /^(\d{4})(\d{2})(\d{2})T(\d{2})(\d{2})(\d{2})Z/.exec(id)
  if (run) {
    const [, y, mo, d, h, mi, s] = run
    return new Date(Date.UTC(+y, +mo - 1, +d, +h, +mi, +s))
  }
  const day = /(?:^|-)(\d{4})(\d{2})(\d{2})(?:-[0-9a-f]{4})?$/.exec(id)
  if (day) {
    const [, y, mo, d] = day
    const date = new Date(+y, +mo - 1, +d)
    return Number.isNaN(date.getTime()) ? null : date
  }
  return null
}

const DAY: Intl.DateTimeFormatOptions = { month: 'short', day: 'numeric', year: 'numeric' }

/** "Run started Oct 6, 2026, 9:18 AM" (local time), or "Pipeline run" if the ID has no date. */
export function runLabel(jobId?: string | null): string {
  const d = jobId ? dateFromId(jobId) : null
  if (!d) return 'Pipeline run'
  return `Run started ${d.toLocaleString(undefined, { ...DAY, hour: 'numeric', minute: '2-digit' })}`
}

/** "Uploaded Oct 5, 2026" for an upload batch or upload project ID. */
export function uploadedLabel(id?: string | null): string {
  const d = id ? dateFromId(id) : null
  return d ? `Uploaded ${d.toLocaleDateString(undefined, DAY)}` : 'Uploaded project'
}

/** File name only, for paths shown to users. */
export function fileName(path?: string | null): string {
  if (!path) return ''
  const parts = path.split(/[\\/]/).filter(Boolean)
  return parts[parts.length - 1] ?? path
}

// Plain-language description of each pipeline stage (the technical notes stay in Technical details).
const STEP_PLAIN: Record<string, string> = {
  parsing: 'Reads the teacher guide and the standards spreadsheet',
  normalization: 'Organises each lesson and standard into a common format',
  embedding: 'Prepares the standards so lessons can be matched to them',
  retrieval: 'Finds the most likely standards for each lesson',
  judge: 'AI checks each lesson against its likely standards, with page evidence',
  results: 'Builds the reports you can download from Exports',
}

export function stepDescription(stepId: string, fallback = ''): string {
  return STEP_PLAIN[stepId] ?? fallback
}

/** Short error codes such as "interrupted" are not sentences; prefer the full message then. */
export function runProblem(error?: string | null, message?: string | null): string {
  const e = (error || '').trim()
  const isSentence = e.includes(' ')
  return (isSentence ? e : message || e) || 'The run stopped without a message. Open Logging for details.'
}
