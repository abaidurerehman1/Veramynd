export type AlignmentStatus = 'full' | 'partial' | 'none'



export interface ProjectInputs {

  guide_pdf: string

  standards_xlsx: string

  guide_pdf_exists: boolean

  standards_xlsx_exists: boolean

}



export interface ProjectCard {

  id: string

  name: string

  publisher: string

  grade: number | null

  subject: string

  module: string

  framework: string

  batch_label: string

  expected_lessons: number | null

  output_dir: string

  inputs: ProjectInputs

  has_output: boolean

  run_status?: 'empty' | 'running' | 'ready'

  is_default: boolean

  source?: 'registry' | 'upload'

  upload_batch_id?: string | null

  can_purge?: boolean

  lessons?: number

  standards_total?: number

  status?: string

}



export interface ProjectsResponse {

  default_project_id: string

  projects: ProjectCard[]

}



export interface OverviewMetrics {

  project_id?: string

  readiness?: 'empty' | 'running' | 'ready'

  last_reviewed?: string | null

  lessons: number

  standards: number

  standards_leaves: number

  alignments: number

  review_required: number

  escalated: number

  alignment_coverage_pct: number

  pipeline_health: string

  by_status: Record<string, number>

  live_job?: {
    id: string
    percent?: number
    current_step?: string | null
    status?: string
  } | null

  grounded: number

  positive_standards_cited: number

  parents_partially_met?: number | null

  source_label?: string

  pdf_quality: PdfQuality

}



export interface PdfQuality {

  available?: boolean

  judge_accuracy?: number | null

  binary_precision?: number | null

  binary_recall?: number | null

  retrieve_recall_at_25?: number | null

  lessons_in_scope?: number

  curriculum_pdf?: string

  standards_set?: string

  project_id?: string

}



export interface LessonCoverageRow {

  resource_id: string

  title: string

  full: number

  partial: number

  none: number

  review: number

  aligned: number

}



export interface LessonDetail {

  code: string

  title: string

  grade?: number | null

  module?: number | null

  unit?: number | null

  lesson?: number | null

  page_start?: number | null

  page_end?: number | null

  learning_targets?: unknown[]

  agenda?: unknown[]

  instructional_blocks?: unknown[]

  materials?: unknown[]

  vocabulary?: unknown[]

  alignments_summary?: Record<string, number>

}



export interface StandardCoverageRow {

  code: string

  level: string

  label: string

  text: string

  parent_code?: string | null

  lessons: string[]

  status: 'covered' | 'partial' | 'not_found' | 'review'

  full: number

  partial: number

  review: number

}



export interface StandardNode {

  code: string

  level: string

  label: string

  text: string

  parent_code?: string | null

  children: StandardNode[]

}



export interface AlignmentRow {

  id: string

  resource_id: string

  lesson_title: string

  standard_code: string

  standard_text: string

  matched_status: AlignmentStatus

  confidence: string

  needs_review: boolean

  review_reason?: string

  evidence?: string

  evidence_page?: number | null

  rationale?: string

  grounded?: boolean

  escalated?: boolean

  judge_model?: string

  prompt_version?: string

  clauses?: unknown[]

  input_scope_caveat?: string | null

  retrieval?: Record<string, unknown>

}



export interface ReviewItem {

  id: string

  resource_id: string

  lesson_title: string

  standard_code: string

  matched_status: AlignmentStatus

  confidence: string

  review_reason: string

  evidence?: string

  evidence_page?: number | null

  escalated?: boolean

  rationale?: string

}



export interface PipelineStage {

  id: string

  name: string

  status: 'complete' | 'warning' | 'pending' | 'skipped'

  detail: string

  count: string

}

