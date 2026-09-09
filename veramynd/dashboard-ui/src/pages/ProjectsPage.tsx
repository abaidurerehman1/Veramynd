import { useEffect } from 'react'
import { Link } from 'react-router-dom'
import { OverviewLoading } from '../components/OverviewStates'
import { ProjectsRunList } from '../components/ProjectsRunList'
import { NONE_PROJECT_ID, useProject } from '../project/ProjectContext'

export function ProjectsPage({ reloadKey = 0 }: { reloadKey?: number }) {
  const { projectId, loading, projects, refreshProjects } = useProject()

  useEffect(() => {
    void refreshProjects()
  }, [reloadKey, refreshProjects])

  if (loading && !projects.length) {
    return (
      <div className="page">
        <OverviewLoading />
      </div>
    )
  }

  return (
    <div className="page">
      <header className="page-header">
        <div>
          <h1>Projects</h1>
          <p>Completed and in-progress pipeline runs. Delete removes the project; Logging stays until you Clear logs.</p>
        </div>
        <div className="header-actions">
          <Link className="btn" to={`/projects/${projectId || NONE_PROJECT_ID}/pipeline`}>
            Pipeline
          </Link>
          <Link className="btn" to={`/projects/${projectId || NONE_PROJECT_ID}/ingestion`}>
            New ingest
          </Link>
        </div>
      </header>

      <ProjectsRunList openTo="overview" />
    </div>
  )
}
