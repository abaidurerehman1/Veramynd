// POST a FormData with upload progress, cancel and a timeout (fetch cannot report upload progress).

export type UploadProgress = { loaded: number; total: number; percent: number }

export type UploadResult = { status: number; body: unknown }

export class UploadCancelled extends Error {
  constructor() {
    super('Upload cancelled.')
    this.name = 'UploadCancelled'
  }
}

export function uploadForm(
  url: string,
  form: FormData,
  opts: {
    onProgress?: (p: UploadProgress) => void
    /** Called once every byte has been sent; the server is now checking and saving. */
    onSent?: () => void
    signal?: AbortSignal
    timeoutMs?: number
  } = {},
): Promise<UploadResult> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest()
    xhr.open('POST', url)
    xhr.withCredentials = true
    xhr.responseType = 'text'
    xhr.timeout = opts.timeoutMs ?? 15 * 60 * 1000

    xhr.upload.onprogress = (e) => {
      if (!e.lengthComputable) return
      opts.onProgress?.({ loaded: e.loaded, total: e.total, percent: Math.min(100, Math.round((100 * e.loaded) / e.total)) })
    }
    xhr.upload.onload = () => opts.onSent?.()
    xhr.onload = () => {
      let body: unknown = {}
      try {
        body = xhr.responseText ? JSON.parse(xhr.responseText) : {}
      } catch {
        body = { message: xhr.responseText?.slice(0, 300) }
      }
      resolve({ status: xhr.status, body })
    }
    xhr.onerror = () =>
      reject(new TypeError('Network error: the upload could not reach the server.'))
    xhr.ontimeout = () =>
      reject(new Error('The upload took too long and was stopped. Check your connection and try again.'))
    xhr.onabort = () => reject(new UploadCancelled())

    if (opts.signal) {
      if (opts.signal.aborted) return xhr.abort()
      opts.signal.addEventListener('abort', () => xhr.abort(), { once: true })
    }
    xhr.send(form)
  })
}
