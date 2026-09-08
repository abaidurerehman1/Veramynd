async function api<T>(path: string): Promise<T> {

  const res = await fetch(path)

  if (!res.ok) {

    const text = await res.text()

    throw new Error(text || `HTTP ${res.status}`)

  }

  return res.json() as Promise<T>

}



function withProject(path: string, projectId?: string): string {

  if (!projectId) return path

  const join = path.includes('?') ? '&' : '?'

  return `${path}${join}project_id=${encodeURIComponent(projectId)}`

}



export { api, withProject }

