import { useCallback, useState } from 'react'
import { BrowserRouter, Navigate, Route, Routes, useLocation, useParams } from 'react-router-dom'
import { AuthProvider, useAuth } from './auth/AuthContext'
import { AppShell } from './components/layout/AppShell'
import { AlignmentsPage } from './pages/AlignmentsPage'
import {
  ForgotPasswordPage,
  LoginPage,
  OAuthCallbackPage,
  ResetPasswordPage,
  SignupPage,
  VerifyEmailPage,
} from './pages/AuthPages'
import { CurriculumPage } from './pages/CurriculumPage'
import { ExportsPage } from './pages/ExportsPage'
import { IngestionPage } from './pages/IngestionPage'
import { LessonPage } from './pages/LessonPage'
import { LoggingPage } from './pages/LoggingPage'
import { NoProjectPage } from './pages/NoProjectPage'
import { OverviewPage } from './pages/OverviewPage'
import { PipelinePage } from './pages/PipelinePage'
import { ProjectsPage } from './pages/ProjectsPage'
import { ReviewPage } from './pages/ReviewPage'
import { SettingsPage } from './pages/SettingsPage'
import { StandardsPage } from './pages/StandardsPage'
import { NONE_PROJECT_ID, ProjectProvider, useProject } from './project/ProjectContext'
import './styles/dashboard.css'

function RequireAuth({ children }: { children: React.ReactNode }) {
  const { user, loading } = useAuth()
  const location = useLocation()
  if (loading) {
    return (
      <div className="auth-page">
        <div className="auth-ambiance" aria-hidden>
          <span className="auth-orb auth-orb-a" />
          <span className="auth-orb auth-orb-b" />
        </div>
        <div className="auth-card glass">
          <img src="/logo.png" alt="Veramynd" className="auth-logo" />
          <p className="auth-sub">Loading workspace…</p>
        </div>
      </div>
    )
  }
  if (!user) return <Navigate to="/login" replace state={{ from: location.pathname }} />
  return children
}

function ProjectShell({ onReload }: { onReload: () => void | Promise<void> }) {
  const { project, hasProject } = useProject()
  const { pathname } = useLocation()
  const name = hasProject ? project?.name || '…' : 'None'
  let section = 'Overview'
  if (pathname.includes('/curriculum/')) section = 'Lesson'
  else if (pathname.includes('/curriculum')) section = 'Curriculum'
  else if (pathname.includes('/standards')) section = 'Standards'
  else if (pathname.includes('/alignments')) section = 'Alignments'
  else if (pathname.includes('/review')) section = 'Review'
  else if (pathname.includes('/exports')) section = 'Exports'
  else if (pathname.includes('/settings')) section = 'Settings'
  else if (/\/projects\/[^/]+\/projects\/?$/.test(pathname)) section = 'Projects'
  else if (pathname.includes('/ingestion')) section = 'Ingestion'
  else if (pathname.includes('/pipeline')) section = 'Pipeline'
  else if (pathname.includes('/logging')) section = 'Logging'
  const crumbs = hasProject
    ? `Veramynd / ${name} / ${section}`
    : section === 'Overview'
      ? 'Veramynd / Workspace'
      : section === 'Settings'
        ? 'Veramynd / System / Settings'
        : section === 'Exports'
          ? 'Veramynd / Output / Exports'
          : `Veramynd / Operations / ${section}`
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

function ReviewRoute({ reloadKey }: { reloadKey: number }) {
  const { projectId } = useParams()
  const { hasProject } = useProject()
  if (!projectId) return <Navigate to="/" replace />
  if (!hasProject) return <Navigate to={`/projects/${NONE_PROJECT_ID}`} replace />
  return <ReviewPage reloadKey={reloadKey} projectId={projectId} />
}

function PipelineRoute({ reloadKey }: { reloadKey: number }) {
  const { projectId } = useParams()
  if (!projectId) return <Navigate to="/" replace />
  return <PipelinePage reloadKey={reloadKey} projectId={projectId} />
}

function ExportsRoute({ reloadKey }: { reloadKey: number }) {
  const { projectId } = useParams()
  if (!projectId) return <Navigate to="/" replace />
  return <ExportsPage reloadKey={reloadKey} projectId={projectId} />
}

export default function App() {
  const [reloadKey, setReloadKey] = useState(0)

  const onReload = useCallback(async () => {
    const stored = localStorage.getItem('veramynd.activeProjectId') || ''
    const q =
      stored && stored !== NONE_PROJECT_ID
        ? `?project_id=${encodeURIComponent(stored)}`
        : ''
    const res = await fetch(`/api/reload${q}`, { method: 'POST', credentials: 'include' })
    if (!res.ok) {
      throw new Error((await res.text()) || `HTTP ${res.status}`)
    }
    setReloadKey((k) => k + 1)
  }, [])

  return (
    <BrowserRouter>
      <AuthProvider>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route path="/signup" element={<SignupPage />} />
          <Route path="/verify-email" element={<VerifyEmailPage />} />
          <Route path="/forgot-password" element={<ForgotPasswordPage />} />
          <Route path="/reset-password" element={<ResetPasswordPage />} />
          <Route path="/oauth/callback" element={<OAuthCallbackPage />} />

          <Route
            path="/projects/:projectId"
            element={
              <RequireAuth>
                <ProjectProvider />
              </RequireAuth>
            }
          >
            <Route element={<ProjectShell onReload={onReload} />}>
              <Route index element={<OverviewRoute reloadKey={reloadKey} />} />
              <Route path="curriculum" element={<CurriculumRoute reloadKey={reloadKey} />} />
              <Route path="curriculum/:lessonCode" element={<LessonPage reloadKey={reloadKey} />} />
              <Route path="standards" element={<StandardsRoute reloadKey={reloadKey} />} />
              <Route path="alignments" element={<AlignmentsRoute reloadKey={reloadKey} />} />
              <Route path="review" element={<ReviewRoute reloadKey={reloadKey} />} />
              <Route path="exports" element={<ExportsRoute reloadKey={reloadKey} />} />
              <Route path="projects" element={<ProjectsPage reloadKey={reloadKey} />} />
              <Route path="ingestion" element={<IngestionPage reloadKey={reloadKey} />} />
              <Route path="pipeline" element={<PipelineRoute reloadKey={reloadKey} />} />
              <Route path="logging" element={<LoggingPage reloadKey={reloadKey} />} />
              <Route
                path="settings"
                element={<SettingsPage reloadKey={reloadKey} onReload={onReload} />}
              />
            </Route>
          </Route>
          <Route path="/ingest" element={<Navigate to={`/projects/${NONE_PROJECT_ID}/ingestion`} replace />} />
          <Route path="/" element={<Navigate to="/projects/el-g1-m2-ga-ela" replace />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </AuthProvider>
    </BrowserRouter>
  )
}
