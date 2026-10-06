// Turn API failures into sentences people can act on, instead of raw JSON or "HTTP 500".

const STATUS_TEXT: Record<number, string> = {
  400: 'The request was not accepted.',
  401: 'Your session has expired. Sign in again.',
  403: 'You do not have permission to do that.',
  404: 'That item could not be found. It may have been deleted.',
  409: 'That action conflicts with something already running. Wait for it to finish and try again.',
  413: 'The file is too large to upload.',
  422: 'Some fields are missing or invalid.',
  500: 'The server hit an unexpected error. Try again; if it keeps happening, check Logging.',
  502: 'The server is not responding right now. Try again in a minute.',
  503: 'The server is busy or restarting. Try again in a minute.',
  504: 'The server took too long to respond. Try again in a minute.',
}

/** Message from a FastAPI-style error body ({ detail }), or a plain-language fallback for the status. */
export function detailMessage(body: unknown, status: number): string {
  const b = (body ?? {}) as { detail?: unknown; message?: unknown }
  const detail = b.detail
  if (typeof detail === 'string' && detail.trim()) return detail
  if (Array.isArray(detail) && detail.length) {
    return detail
      .map((d: { msg?: string; loc?: unknown[] }) => {
        const field = Array.isArray(d.loc) ? d.loc.filter((x) => x !== 'body').join('.') : ''
        return field ? `${field}: ${d.msg ?? 'invalid'}` : (d.msg ?? 'Invalid value')
      })
      .join('; ')
  }
  if (typeof b.message === 'string' && b.message.trim()) return b.message
  return STATUS_TEXT[status] ?? `Request failed (HTTP ${status}).`
}

/** Build an Error from a failed fetch Response, reading JSON detail when present. */
export async function responseError(res: Response): Promise<Error> {
  const text = await res.text().catch(() => '')
  let body: unknown = null
  try {
    body = text ? JSON.parse(text) : null
  } catch {
    body = null
  }
  // Plain-text bodies (not HTML error pages) are already readable.
  const plain = !body && text && !/^\s*</.test(text) ? text.slice(0, 300) : ''
  return new Error(plain || detailMessage(body, res.status))
}

/** Readable text for any thrown value, including network failures. */
export function friendlyError(e: unknown): string {
  if (e instanceof TypeError && /fetch|network|load failed/i.test(e.message)) {
    return 'Cannot reach the Veramynd server. Check your connection, or that the backend is running, and try again.'
  }
  if (e instanceof Error) return e.message || 'Something went wrong.'
  return String(e || 'Something went wrong.')
}
