import { useCallback, useState } from 'react'
import { BrowserRouter, Navigate, Route, Routes, useLocation, useParams } from 'react-router-dom'
import { AppShell } from './components/layout/AppShell'
import { AlignmentsPage } from './pages/AlignmentsPage'
import { CurriculumPage } from './pages/CurriculumPage'
import { LessonPage } from './pages/LessonPage'
import { NoProjectPage } from './pages/NoProjectPage'
import { OverviewPage } from './pages/OverviewPage'
import { StandardsPage } from './pages/StandardsPage'
import { NONE_PROJECT_ID, ProjectProvider, useProject } from './project/ProjectContext'
import './styles/dashboard.css'

function ProjectShell({ onReload }: { onReload: () => void }) {
  const { project, hasProject } = useProject()
  const { pathname } = useLocation()
  const name = hasProject ? project?.name || '…' : 'None'
  let section = 'Overview'
  if (pathname.includes('/curriculum/')) section = 'Lesson'
  else if (pathname.includes('/curriculum')) section = 'Curriculum'
  else if (pathname.includes('/standards')) section = 'Standards'
  else if (pathname.includes('/alignments')) section = 'Alignments'
  const crumbs = hasProject ? `Veramynd / ${name} / ${section}` : 'Veramynd / No project'
  return <AppShell crumbs={crumbs} onReload={onReload} />
}

function OverviewRoute({ reloadKey }: { reloadKey: number }) {
  const { projectId } = useParams()
  const { hasProject } = useProject()
  if (!projectId) return <Navigate to="/" replace />
  if (!hasProject || projectId === NONE_PROJECT_ID) return <NoProjectPage />
  return <OverviewPage reloadKey={reloadKey} projectId={projectId} />
}

function CurriculumRoute({ reloadKey }: { reloadKey: number }) {
  const { projectId } = useParams()
  const { hasProject } = useProject()
  if (!projectId) return <Navigate to="/" replace />
  if (!hasProject) return <Navigate to={`/projects/${NONE_PROJECT_ID}`} replace />
  return <CurriculumPage reloadKey={reloadKey} projectId={projectId} />
}

function StandardsRoute({ reloadKey }: { reloadKey: number }) {
  const { projectId } = useParams()
  const { hasProject } = useProject()
  if (!projectId) return <Navigate to="/" replace />
  if (!hasProject) return <Navigate to={`/projects/${NONE_PROJECT_ID}`} replace />
  return <StandardsPage reloadKey={reloadKey} projectId={projectId} />
}

function AlignmentsRoute({ reloadKey }: { reloadKey: number }) {
  const { projectId } = useParams()
  const { hasProject } = useProject()
  if (!projectId) return <Navigate to="/" replace />
  if (!hasProject) return <Navigate to={`/projects/${NONE_PROJECT_ID}`} replace />
  return <AlignmentsPage reloadKey={reloadKey} projectId={projectId} />
}

export default function App() {
  const [reloadKey, setReloadKey] = useState(0)

  const onReload = useCallback(() => {
    const stored = localStorage.getItem('veramynd.activeProjectId') || ''
    const q =
      stored && stored !== NONE_PROJECT_ID
        ? `?project_id=${encodeURIComponent(stored)}`
        : ''
    void fetch(`/api/reload${q}`, { method: 'POST' }).finally(() => {
      setReloadKey((k) => k + 1)
    })
  }, [])

  return (
    <BrowserRouter>
      <Routes>
        <Route path="/projects/:projectId" element={<ProjectProvider />}>
          <Route element={<ProjectShell onReload={onReload} />}>
            <Route index element={<OverviewRoute reloadKey={reloadKey} />} />
            <Route path="curriculum" element={<CurriculumRoute reloadKey={reloadKey} />} />
            <Route path="curriculum/:lessonCode" element={<LessonPage reloadKey={reloadKey} />} />
            <Route path="standards" element={<StandardsRoute reloadKey={reloadKey} />} />
            <Route path="alignments" element={<AlignmentsRoute reloadKey={reloadKey} />} />
          </Route>
        </Route>
        <Route path="/" element={<Navigate to="/projects/el-g1-m2-ga-ela" replace />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  )
}
