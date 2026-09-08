import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'
import { Outlet, useNavigate, useParams } from 'react-router-dom'
import { api } from '../api/client'
import type { ProjectCard, ProjectsResponse } from '../api/types'

export const NONE_PROJECT_ID = 'none'

type ProjectContextValue = {
  projects: ProjectCard[]
  defaultProjectId: string
  projectId: string
  project: ProjectCard | null
  hasProject: boolean
  loading: boolean
  error: string | null
  setProjectId: (id: string) => void
  clearProject: () => void
  refreshProjects: () => Promise<void>
}

const ProjectContext = createContext<ProjectContextValue | null>(null)

const STORAGE_KEY = 'veramynd.activeProjectId'

export function ProjectProvider({ children }: { children?: ReactNode }) {
  const { projectId: routeProjectId = '' } = useParams()
  const navigate = useNavigate()
  const [projects, setProjects] = useState<ProjectCard[]>([])
  const [defaultProjectId, setDefaultProjectId] = useState('el-g1-m2-ga-ela')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const hasProject = Boolean(routeProjectId) && routeProjectId !== NONE_PROJECT_ID

  const refreshProjects = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const data = await api<ProjectsResponse>('/api/projects')
      setProjects(data.projects)
      setDefaultProjectId(data.default_project_id)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void refreshProjects()
  }, [refreshProjects])

  useEffect(() => {
    if (routeProjectId) {
      localStorage.setItem(STORAGE_KEY, routeProjectId)
    }
  }, [routeProjectId])

  useEffect(() => {
    if (!projects.length || !routeProjectId) return
    if (routeProjectId === NONE_PROJECT_ID) return
    if (!projects.some((p) => p.id === routeProjectId)) {
      navigate(`/projects/${defaultProjectId}`, { replace: true })
    }
  }, [projects, routeProjectId, defaultProjectId, navigate])

  const setProjectId = useCallback(
    (id: string) => {
      localStorage.setItem(STORAGE_KEY, id)
      navigate(`/projects/${id}`)
    },
    [navigate],
  )

  const clearProject = useCallback(() => {
    localStorage.setItem(STORAGE_KEY, NONE_PROJECT_ID)
    navigate(`/projects/${NONE_PROJECT_ID}`)
  }, [navigate])

  const project = useMemo(
    () => (hasProject ? projects.find((p) => p.id === routeProjectId) || null : null),
    [projects, routeProjectId, hasProject],
  )

  const value = useMemo(
    () => ({
      projects,
      defaultProjectId,
      projectId: routeProjectId,
      project,
      hasProject,
      loading,
      error,
      setProjectId,
      clearProject,
      refreshProjects,
    }),
    [
      projects,
      defaultProjectId,
      routeProjectId,
      project,
      hasProject,
      loading,
      error,
      setProjectId,
      clearProject,
      refreshProjects,
    ],
  )

  return (
    <ProjectContext.Provider value={value}>
      {children ?? <Outlet />}
    </ProjectContext.Provider>
  )
}

export function useProject() {
  const ctx = useContext(ProjectContext)
  if (!ctx) throw new Error('useProject must be used within ProjectProvider')
  return ctx
}
