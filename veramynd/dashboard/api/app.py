"""Enterprise dashboard API — read-only over Veramynd output artifacts."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from .catalog import get_catalog, reload_catalog
from .projects import (
    default_project_id,
    list_project_configs,
    project_card,
    get_project_config,
    reload_registry,
)

DASHBOARD_ROOT = Path(__file__).resolve().parents[1]
WEB_DIR = DASHBOARD_ROOT / "web"
ASSETS_DIR = WEB_DIR / "assets"
UPLOADS_DIR = DASHBOARD_ROOT / "uploads"

_MAX_UPLOAD_BYTES = 200 * 1024 * 1024
_SAFE_NAME = re.compile(r"[^A-Za-z0-9._-]+")

app = FastAPI(title="Veramynd Alignment Dashboard", version="1.1.0")


def _catalog(project_id: str | None):
    try:
        cat = get_catalog(project_id)
    except KeyError as e:
        raise HTTPException(404, str(e)) from e
    cat.ensure()
    return cat


@app.on_event("startup")
def _startup() -> None:
    get_catalog().ensure()


@app.get("/", response_class=HTMLResponse)
def index() -> HTMLResponse:
    index_path = WEB_DIR / "index.html"
    if not index_path.is_file():
        raise HTTPException(500, "web/index.html missing")
    return HTMLResponse(index_path.read_text(encoding="utf-8"))


@app.get("/api/health")
def health(project_id: str | None = None) -> dict:
    cat = _catalog(project_id)
    return {
        "ok": cat.error is None,
        "error": cat.error,
        "project_id": cat.config.id,
        "default_project_id": default_project_id(),
        "lessons": len(cat.lessons),
        "alignments": len(cat.alignments),
    }


@app.post("/api/reload")
def reload_api(project_id: str | None = None) -> dict:
    reload_registry()
    try:
        cat = reload_catalog(project_id)
    except KeyError as e:
        raise HTTPException(404, str(e)) from e
    cat.ensure()
    return health(project_id=cat.config.id)


@app.get("/api/projects")
def projects() -> dict:
    """List registered projects. One Overview = one project."""
    rows = [project_card(cfg) for cfg in list_project_configs()]
    return {
        "default_project_id": default_project_id(),
        "projects": rows,
    }


@app.get("/api/projects/{project_id}")
def project_detail(project_id: str) -> dict:
    try:
        cfg = get_project_config(project_id)
    except KeyError as e:
        raise HTTPException(404, str(e)) from e
    cat = _catalog(project_id)
    if cat.error:
        card = project_card(cfg)
        card["status"] = "error"
        card["error"] = cat.error
        return card
    summary = cat.project().model_dump()
    summary.update(
        {
            "has_output": project_card(cfg)["has_output"],
            "is_default": cfg.id == default_project_id(),
        }
    )
    return summary


@app.get("/api/project")
def project(project_id: str | None = None) -> dict:
    cat = _catalog(project_id)
    if cat.error:
        raise HTTPException(503, cat.error)
    return cat.project().model_dump()


@app.get("/api/overview")
def overview(project_id: str | None = None) -> dict:
    cat = _catalog(project_id)
    if cat.error:
        raise HTTPException(503, cat.error)
    return cat.overview().model_dump()


@app.get("/api/quality")
def quality(project_id: str | None = None) -> dict:
    """Accuracy + recall for the project's curriculum PDF (computed from artifacts)."""
    cat = _catalog(project_id)
    if cat.error:
        raise HTTPException(503, cat.error)
    return cat.pdf_quality()


@app.get("/api/lessons/coverage")
def lessons_coverage(project_id: str | None = None) -> dict:
    cat = _catalog(project_id)
    return {"project_id": cat.config.id, "rows": [r.model_dump() for r in cat.lesson_coverage()]}


@app.get("/api/lessons/{code}")
def lesson_detail(code: str, project_id: str | None = None) -> dict:
    cat = _catalog(project_id)
    detail = cat.lesson_detail(code)
    if not detail:
        raise HTTPException(404, "Lesson not found")
    return detail.model_dump()


@app.get("/api/standards/coverage")
def standards_coverage(project_id: str | None = None) -> dict:
    cat = _catalog(project_id)
    return {"project_id": cat.config.id, "rows": [r.model_dump() for r in cat.standard_coverage()]}


@app.get("/api/standards/tree")
def standards_tree(project_id: str | None = None) -> dict:
    cat = _catalog(project_id)
    return {"project_id": cat.config.id, "roots": [n.model_dump() for n in cat.standards_tree()]}


@app.get("/api/alignments")
def alignments(
    project_id: str | None = None,
    status: str | None = None,
    lesson: str | None = None,
    q: str | None = None,
    needs_review: bool | None = None,
    limit: int = Query(200, ge=1, le=2000),
    offset: int = Query(0, ge=0),
) -> dict:
    cat = _catalog(project_id)
    rows, total = cat.list_alignments(
        status=status,
        lesson=lesson,
        q=q,
        needs_review=needs_review,
        limit=limit,
        offset=offset,
    )
    return {
        "project_id": cat.config.id,
        "total": total,
        "rows": [r.model_dump() for r in rows],
    }


@app.get("/api/alignments/{alignment_id:path}")
def alignment_detail(alignment_id: str, project_id: str | None = None) -> dict:
    cat = _catalog(project_id)
    row = cat.get_alignment(alignment_id)
    if not row:
        raise HTTPException(404, "Alignment not found")
    return row.model_dump()


@app.get("/api/evidence")
def evidence(
    project_id: str | None = None,
    lesson: str | None = None,
    status: str | None = None,
    q: str | None = None,
    limit: int = Query(100, ge=1, le=500),
) -> dict:
    cat = _catalog(project_id)
    return {
        "project_id": cat.config.id,
        "rows": [
            r.model_dump()
            for r in cat.evidence(lesson=lesson, status=status, q=q, limit=limit)
        ],
    }


@app.get("/api/review")
def review_queue(project_id: str | None = None) -> dict:
    cat = _catalog(project_id)
    return {"project_id": cat.config.id, "rows": [r.model_dump() for r in cat.review_queue()]}


@app.get("/api/pipeline")
def pipeline(project_id: str | None = None) -> dict:
    cat = _catalog(project_id)
    return {"project_id": cat.config.id, "stages": [s.model_dump() for s in cat.pipeline()]}


@app.get("/api/runs")
def runs(project_id: str | None = None) -> dict:
    cat = _catalog(project_id)
    return {"project_id": cat.config.id, "rows": [r.model_dump() for r in cat.runs()]}


@app.get("/api/qa")
def qa(project_id: str | None = None) -> dict:
    cat = _catalog(project_id)
    return cat.qa_metrics().model_dump()


@app.get("/api/exports")
def exports(project_id: str | None = None) -> dict:
    cat = _catalog(project_id)
    return {"project_id": cat.config.id, "rows": [e.model_dump() for e in cat.exports()]}


@app.get("/api/exports/{export_id}/download")
def export_download(export_id: str, project_id: str | None = None) -> FileResponse:
    cat = _catalog(project_id)
    path = cat.export_path(export_id)
    if not path or not path.is_file():
        raise HTTPException(404, "Export not available")
    return FileResponse(path, filename=path.name)


@app.get("/api/search")
def search(
    q: str = "",
    project_id: str | None = None,
    limit: int = Query(30, ge=1, le=100),
) -> dict:
    cat = _catalog(project_id)
    return {"project_id": cat.config.id, "hits": cat.search(q, limit=limit)}


def _safe_filename(name: str, fallback: str) -> str:
    base = Path(name or "").name
    cleaned = _SAFE_NAME.sub("_", base).strip("._") or fallback
    return cleaned[:180]


@app.get("/api/ingest")
def ingest_status() -> dict:
    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    batches = []
    for p in sorted(UPLOADS_DIR.iterdir(), reverse=True):
        if not p.is_dir():
            continue
        files = [f.name for f in p.iterdir() if f.is_file()]
        batches.append({"id": p.name, "files": files})
        if len(batches) >= 10:
            break
    return {
        "uploads_dir": str(UPLOADS_DIR),
        "note": "Uploads are stored under dashboard/uploads only. They do not overwrite project output folders.",
        "batches": batches,
    }


@app.post("/api/ingest")
async def ingest_upload(
    program_name: str = Form("EL Education Curriculum"),
    guide_label: str = Form("Module 2"),
    grade_label: str = Form("Grade 1"),
    guide_pdf: UploadFile | None = File(None),
    standards_xlsx: UploadFile | None = File(None),
) -> dict:
    """Accept curriculum inputs for the workspace (storage only — no pipeline run)."""
    if not guide_pdf and not standards_xlsx:
        raise HTTPException(400, "Upload a teacher-guide PDF and/or standards XLSX")

    batch_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    dest = UPLOADS_DIR / batch_id
    dest.mkdir(parents=True, exist_ok=True)
    saved: list[str] = []

    async def _save(upload: UploadFile, fallback: str, allowed: tuple[str, ...]) -> str:
        name = _safe_filename(upload.filename or "", fallback)
        lower = name.lower()
        if not any(lower.endswith(ext) for ext in allowed):
            raise HTTPException(400, f"{fallback} must be one of {', '.join(allowed)}")
        data = await upload.read()
        if not data:
            raise HTTPException(400, f"{fallback} is empty")
        if len(data) > _MAX_UPLOAD_BYTES:
            raise HTTPException(400, f"{fallback} exceeds 200 MB limit")
        path = dest / name
        path.write_bytes(data)
        saved.append(name)
        return name

    try:
        if guide_pdf and guide_pdf.filename:
            await _save(guide_pdf, "guide.pdf", (".pdf",))
        if standards_xlsx and standards_xlsx.filename:
            await _save(standards_xlsx, "standards.xlsx", (".xlsx", ".xlsm"))
        meta = {
            "program_name": (program_name or "").strip(),
            "guide_label": (guide_label or "").strip(),
            "grade_label": (grade_label or "").strip(),
            "files": saved,
        }
        (dest / "meta.json").write_text(
            __import__("json").dumps(meta, indent=2) + "\n", encoding="utf-8"
        )
    except HTTPException:
        raise
    except OSError as e:
        raise HTTPException(500, f"Could not save upload: {e}") from e

    return {
        "ok": True,
        "batch_id": batch_id,
        "files": saved,
        "message": "Inputs saved. Full parse→judge still runs via CLI; dashboard Overview is scoped per project.",
    }


if ASSETS_DIR.is_dir():
    app.mount("/assets", StaticFiles(directory=str(ASSETS_DIR)), name="assets")
