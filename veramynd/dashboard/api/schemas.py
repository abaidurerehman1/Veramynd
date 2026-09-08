"""Typed shapes for dashboard API responses (mirror real artifact fields)."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

AlignmentStatus = Literal["full", "partial", "none"]


class ProjectInputs(BaseModel):
    guide_pdf: str = ""
    standards_xlsx: str = ""
    guide_pdf_exists: bool = False
    standards_xlsx_exists: bool = False


class ProjectSummary(BaseModel):
    id: str
    name: str
    publisher: str
    grade: int | None = None
    subject: str
    module: str
    lessons: int
    standards_total: int
    standards_leaves: int
    status: str
    last_processed: str | None = None
    framework: str = ""
    batch_label: str = ""
    expected_lessons: int | None = None
    output_dir: str = ""
    inputs: ProjectInputs = Field(default_factory=ProjectInputs)


class OverviewMetrics(BaseModel):
    project_id: str = ""
    readiness: Literal["empty", "running", "ready"] = "empty"
    last_reviewed: str | None = None
    lessons: int
    standards: int
    standards_leaves: int
    alignments: int
    review_required: int
    escalated: int
    alignment_coverage_pct: float
    pipeline_health: str
    by_status: dict[str, int]
    grounded: int
    positive_standards_cited: int
    parents_partially_met: int | None = None
    source_label: str = ""
    pdf_quality: dict[str, Any] = Field(default_factory=dict)

class LessonCoverageRow(BaseModel):
    resource_id: str
    title: str
    full: int
    partial: int
    none: int
    review: int
    aligned: int  # full + partial


class StandardCoverageRow(BaseModel):
    code: str
    level: str
    label: str
    text: str
    parent_code: str | None = None
    lessons: list[str] = Field(default_factory=list)
    status: Literal["covered", "partial", "not_found", "review"]
    full: int = 0
    partial: int = 0
    review: int = 0


class AlignmentRow(BaseModel):
    id: str
    resource_id: str
    lesson_title: str
    standard_code: str
    standard_text: str
    matched_status: AlignmentStatus
    confidence: str
    needs_review: bool
    review_reason: str = ""
    evidence: str = ""
    evidence_page: int | None = None
    rationale: str = ""
    grounded: bool = False
    escalated: bool = False
    judge_model: str = ""
    prompt_version: str = ""
    clauses: list[dict[str, Any]] = Field(default_factory=list)
    input_scope_caveat: str | None = None
    retrieval: dict[str, Any] = Field(default_factory=dict)


class EvidenceRow(BaseModel):
    id: str
    resource_id: str
    lesson_title: str
    standard_code: str
    matched_status: AlignmentStatus
    evidence: str
    evidence_page: int | None = None
    section_hint: str = ""
    needs_review: bool = False


class ReviewItem(BaseModel):
    id: str
    resource_id: str
    lesson_title: str
    standard_code: str
    matched_status: AlignmentStatus
    confidence: str
    review_reason: str
    evidence: str = ""
    evidence_page: int | None = None
    escalated: bool = False
    rationale: str = ""


class PipelineStage(BaseModel):
    id: str
    name: str
    status: Literal["complete", "warning", "pending", "skipped"]
    detail: str
    count: str = ""


class RunRow(BaseModel):
    id: str
    curriculum: str
    standards_set: str
    lessons: int
    alignments: int
    status: str
    started: str | None = None
    duration: str | None = None
    source: str = ""


class LessonDetail(BaseModel):
    code: str
    title: str
    grade: int | None = None
    module: int | None = None
    unit: int | None = None
    lesson: int | None = None
    page_start: int | None = None
    page_end: int | None = None
    learning_targets: list[Any] = Field(default_factory=list)
    agenda: list[Any] = Field(default_factory=list)
    instructional_blocks: list[Any] = Field(default_factory=list)
    materials: list[Any] = Field(default_factory=list)
    vocabulary: list[Any] = Field(default_factory=list)
    alignments_summary: dict[str, int] = Field(default_factory=dict)


class StandardNode(BaseModel):
    code: str
    level: str
    label: str
    text: str
    parent_code: str | None = None
    children: list["StandardNode"] = Field(default_factory=list)


class QaMetrics(BaseModel):
    retrieval: dict[str, Any] = Field(default_factory=dict)
    alignment: dict[str, Any] = Field(default_factory=dict)
    human_qa: dict[str, Any] = Field(default_factory=dict)
    notes: list[str] = Field(default_factory=list)


class ExportItem(BaseModel):
    id: str
    name: str
    type: str
    path: str
    available: bool
    download_url: str | None = None
