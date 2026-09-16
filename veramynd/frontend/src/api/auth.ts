import { api } from './client'

export type AuthUser = {
  id: number
  name: string
  email: string
  email_verified: boolean
  oauth_provider?: string | null
  avatar_url?: string | null
}

export async function authApi<T>(
  path: string,
  opts?: RequestInit & { json?: unknown },
): Promise<T> {
  const headers: Record<string, string> = {
    ...(opts?.headers as Record<string, string> | undefined),
  }
  let body = opts?.body
  if (opts && 'json' in opts && opts.json !== undefined) {
    headers['Content-Type'] = 'application/json'
    body = JSON.stringify(opts.json)
  }
  const res = await fetch(path, {
    ...opts,
    headers,
    body,
    credentials: 'include',
  })
  const text = await res.text()
  let data: unknown = null
  try {
    data = text ? JSON.parse(text) : null
  } catch {
    data = { detail: text }
  }
  if (!res.ok) {
    let detail = text || `HTTP ${res.status}`
    if (typeof data === 'object' && data && 'detail' in data) {
      const d = (data as { detail: unknown }).detail
      if (typeof d === 'string') detail = d
      else if (Array.isArray(d)) {
        detail = d
          .map((item) => {
            if (typeof item === 'object' && item && 'msg' in item) return String((item as { msg: string }).msg)
            return String(item)
          })
          .join('; ')
      }
    }
    throw new Error(detail)
  }
  return data as T
}

export async function fetchMe(): Promise<AuthUser | null> {
  try {
    const res = await authApi<{ user: AuthUser }>('/api/auth/me')
    return res.user
  } catch {
    return null
  }
}

export async function uploadAvatar(file: File): Promise<AuthUser> {
  const form = new FormData()
  form.append('file', file)
  const res = await authApi<{ user: AuthUser }>('/api/auth/avatar', {
    method: 'POST',
    body: form,
  })
  return res.user
}

export async function removeAvatar(): Promise<AuthUser> {
  const res = await authApi<{ user: AuthUser }>('/api/auth/avatar', {
    method: 'DELETE',
  })
  return res.user
}

export { api }
