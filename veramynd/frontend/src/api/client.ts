import { responseError } from '../lib/errors'

async function api<T>(path: string): Promise<T> {

  const res = await fetch(path)

  if (!res.ok) {

    // Session expired or signed out elsewhere: go to sign-in instead of showing errors.
    if (res.status === 401 && !window.location.pathname.startsWith('/login')) {
      window.location.assign(`/login?next=${encodeURIComponent(window.location.pathname)}`)
    }

    throw await responseError(res)

  }

  return res.json() as Promise<T>

}



function withProject(path: string, projectId?: string): string {

  if (!projectId) return path

  const join = path.includes('?') ? '&' : '?'

  return `${path}${join}project_id=${encodeURIComponent(projectId)}`

}



export { api, withProject }

