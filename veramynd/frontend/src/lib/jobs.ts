/** A pipeline job holds the single run slot while queued, running or paused. */
export function isJobActive(status?: string | null) {
  return status === 'running' || status === 'queued' || status === 'paused'
}
