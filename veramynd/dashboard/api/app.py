"""Enterprise dashboard API — artifacts + pipeline job runner."""

from __future__ import annotations

import json
import io
import re
import shutil
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .projects import (
    default_project_id,
    delete_project,
    list_project_configs,
    project_card,
    get_project_config,
    reload_registry,
    upload_project_id,
)
from .catalog import drop_catalog, get_catalog, reload_catalog
from . import pipeline_runner

DASHBOARD_ROOT = Path(__file__).resolve().parents[1]
WEB_DIR = DASHBOARD_ROOT / "web"
ASSETS_DIR = WEB_DIR / "assets"
UI_DIST = DASHBOARD_ROOT.parent / "dashboard-ui" / "dist"
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
    pipeline_runner.recover_interrupted_jobs()
    get_catalog().ensure()


@app.get("/", response_class=HTMLResponse)
def index() -> HTMLResponse:
    """Prefer the React build; API-only message when dist is not built."""
    spa = UI_DIST / "index.html"
    if spa.is_file():
        return HTMLResponse(spa.read_text(encoding="utf-8"))
    return HTMLResponse(
        """<!doctype html>
<html lang="en"><head><meta charset="utf-8"/><title>Veramynd Dashboard</title>
<style>body{font-family:system-ui,sans-serif;max-width:40rem;margin:3rem auto;padding:0 1rem;line-height:1.5;color:#15202b}
code{background:#f4f5f8;padding:0.15em 0.4em;border-radius:6px}</style></head>
<body>
<h1>Veramynd API</h1>
<p>This process serves the API only. Use the React app:</p>
<pre><code>cd veramynd/dashboard-ui
npm run dev</code></pre>
<p>The Vite app proxies <code>/api</code> to this server automatically.</p>
</body></html>""",
        status_code=200,
    )


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
    """List registered projects plus upload batches (virtual projects)."""
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
    card = project_card(cfg)
    cat = _catalog(project_id)
    if cat.error:
        card["status"] = "error"
        card["error"] = cat.error
        return card
    summary = cat.project().model_dump()
    summary.update(
        {
            "has_output": card["has_output"],
            "run_status": card.get("run_status"),
            "is_default": cfg.id == default_project_id(),
            "source": cfg.source,
            "upload_batch_id": cfg.upload_batch_id or None,
            "can_purge": card.get("can_purge"),
        }
    )
    return summary


@app.delete("/api/projects/{project_id}")
def project_delete(project_id: str) -> dict:
    """Delete a completed (or listed) project.

    Upload projects purge ``uploads/<batch>/``. Registry projects are removed from
    ``projects.json`` only (locked Batch-1 artifacts stay on disk).
    """
    try:
        result = delete_project(project_id)
    except KeyError as e:
        raise HTTPException(404, str(e)) from e
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    except OSError as e:
        raise HTTPException(500, f"Could not delete project: {e}") from e
    drop_catalog(project_id)
    # Keep pipeline jobs/logs — only Clear logs removes them.
    return result


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
    data = cat.overview().model_dump()
    # If a live job targets this project/upload, surface "running"
    active = pipeline_runner.active_job()
    if active and active.status in ("queued", "running"):
        from .projects import batch_id_from_project, upload_project_id

        pid = cat.config.id
        batch = batch_id_from_project(pid)
        matches = (active.project_id == pid) or (
            batch and active.batch_id == batch
        ) or (active.batch_id and pid == upload_project_id(active.batch_id))
        if matches and data.get("readiness") != "ready":
            data["readiness"] = "running"
            data["pipeline_health"] = "In progress"
            data["live_job"] = {
                "id": active.id,
                "percent": active.to_dict().get("percent"),
                "current_step": active.current_step,
                "status": active.status,
            }
    return data


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
    completed = pipeline_runner.artifact_completed_steps(cat.config.output_dir)
    return {
        "project_id": cat.config.id,
        "stages": [s.model_dump() for s in cat.pipeline()],
        "runnable_steps": pipeline_runner.list_runnable_steps(),
        "completed_steps": completed,
        "next_step": next(
            (s["id"] for s in pipeline_runner.list_runnable_steps() if s["id"] not in completed),
            None,
        ),
    }


class PipelineRunRequest(BaseModel):
    """Start a real CLI pipeline run. confirm must be true."""

    confirm: bool = False
    mode: str = Field(..., description="full | step")
    step: str | None = None
    batch_id: str | None = None
    project_id: str | None = None
    framework: str = ""


@app.post("/api/pipeline/run")
def pipeline_run(body: PipelineRunRequest) -> dict[str, Any]:
    try:
        job = pipeline_runner.start_job(
            mode=body.mode,
            step=body.step,
            batch_id=body.batch_id,
            project_id=body.project_id,
            framework=body.framework or "",
            confirm=body.confirm,
        )
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    except RuntimeError as e:
        raise HTTPException(409, str(e)) from e
    except KeyError as e:
        raise HTTPException(404, str(e)) from e
    return {"ok": True, "job": job.to_dict()}


@app.get("/api/pipeline/jobs")
def pipeline_jobs(limit: int = Query(20, ge=1, le=100)) -> dict:
    active = pipeline_runner.active_job()
    return {
        "jobs": pipeline_runner.list_jobs(limit=limit),
        "active_job": active.to_dict() if active else None,
        "runnable_steps": pipeline_runner.list_runnable_steps(),
    }


@app.get("/api/pipeline/jobs/{job_id}")
def pipeline_job(job_id: str, log: bool = Query(True)) -> dict:
    job = pipeline_runner.get_job(job_id)
    if not job:
        raise HTTPException(404, f"Unknown job: {job_id}")
    out: dict[str, Any] = {"job": job.to_dict()}
    if log:
        out["log"] = pipeline_runner.job_log_tail(job_id)
    return out


@app.get("/api/pipeline/logs")
def pipeline_logs(
    job_id: str | None = None,
    limit: int = Query(30, ge=1, le=100),
) -> dict:
    """Typed log entries (errors/warnings) across recent pipeline jobs."""
    return pipeline_runner.analyze_job_logs(job_id, limit_jobs=limit)


@app.delete("/api/pipeline/logs")
def pipeline_logs_clear() -> dict:
    """Clear all pipeline job records and log files under ``dashboard/runs/``."""
    return pipeline_runner.clear_all_jobs()


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
def export_download(export_id: str, project_id: str | None = None):
    cat = _catalog(project_id)
    # Folder of per-lesson CSVs → zip stream
    if export_id == "result-csvs":
        files = cat.result_csv_paths()
        if not files:
            raise HTTPException(404, "No result CSVs available")
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for f in files:
                zf.write(f, arcname=f.name)
        buf.seek(0)
        name = f"{cat.config.id}-result-csvs.zip"
        return StreamingResponse(
            buf,
            media_type="application/zip",
            headers={"Content-Disposition": f'attachment; filename="{name}"'},
        )

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


def _slug_part(text: str, max_len: int = 28) -> str:
    raw = (text or "").strip().lower()
    cleaned = _SAFE_NAME.sub("-", raw).strip("-._")
    cleaned = re.sub(r"-{2,}", "-", cleaned)
    return (cleaned or "project")[:max_len].strip("-")


def _make_batch_id(program_name: str, guide_label: str, grade_label: str) -> str:
    """Human-readable batch folder id, unique under uploads/."""
    parts = [
        _slug_part(program_name, 24) if (program_name or "").strip() else "",
        _slug_part(guide_label, 18) if (guide_label or "").strip() else "",
        _slug_part(grade_label, 14) if (grade_label or "").strip() else "",
    ]
    parts = [p for p in parts if p and p != "project"]
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d")
    base = "-".join(parts) if parts else f"upload-{uuid4().hex[:8]}"
    candidate = f"{base}-{stamp}"[:72]
    if not (UPLOADS_DIR / candidate).exists():
        return candidate
    return f"{candidate}-{uuid4().hex[:4]}"[:80]


def _batch_display_name(program_name: str, guide_label: str, grade_label: str) -> str:
    bits = [b for b in [(program_name or "").strip(), (guide_label or "").strip(), (grade_label or "").strip()] if b]
    return " · ".join(bits) or "Untitled upload"


@app.get("/api/ingest")
def ingest_status() -> dict:
    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    batches = []
    for p in sorted(UPLOADS_DIR.iterdir(), reverse=True):
        if not p.is_dir():
            continue
        files = [f.name for f in p.iterdir() if f.is_file()]
        display_name = p.name
        meta_path = p / "meta.json"
        if meta_path.is_file():
            try:
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
                display_name = str(
                    meta.get("display_name")
                    or _batch_display_name(
                        str(meta.get("program_name") or ""),
                        str(meta.get("guide_label") or ""),
                        str(meta.get("grade_label") or ""),
                    )
                )
            except (OSError, json.JSONDecodeError, TypeError):
                display_name = p.name
        batches.append({"id": p.name, "name": display_name, "files": files})
        if len(batches) >= 10:
            break
    return {
        "uploads_dir": str(UPLOADS_DIR),
        "note": (
            "Uploads are stored under dashboard/uploads and appear as projects after a run, "
            "but never auto-run. You must explicitly start Complete auto or step-by-step "
            "(confirm each time)."
        ),
        "batches": batches,
        "runnable_steps": pipeline_runner.list_runnable_steps(),
    }


@app.post("/api/ingest")
async def ingest_upload(
    program_name: str = Form(""),
    guide_label: str = Form(""),
    grade_label: str = Form(""),
    guide_pdf: UploadFile | None = File(None),
    standards_xlsx: UploadFile | None = File(None),
) -> dict:
    """Accept curriculum inputs for the workspace (storage only — no pipeline run)."""
    if not guide_pdf or not guide_pdf.filename or not standards_xlsx or not standards_xlsx.filename:
        raise HTTPException(400, "Both a curriculum PDF and a standards XLSX are required")

    program = (program_name or "").strip()
    guide = (guide_label or "").strip()
    grade = (grade_label or "").strip()
    display_name = _batch_display_name(program, guide, grade)
    batch_id = _make_batch_id(program, guide, grade)
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
        if len(saved) < 2:
            raise HTTPException(400, "Both a curriculum PDF and a standards XLSX are required")
        meta = {
            "program_name": program,
            "guide_label": guide,
            "grade_label": grade,
            "display_name": display_name,
            "files": saved,
        }
        (dest / "meta.json").write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    except HTTPException:
        raise
    except OSError as e:
        raise HTTPException(500, f"Could not save upload: {e}") from e

    return {
        "ok": True,
        "batch_id": batch_id,
        "batch_name": display_name,
        "project_id": upload_project_id(batch_id),
        "files": saved,
        "message": (
            f"Saved “{display_name}”. Pipeline did NOT start — "
            "explicitly run Complete auto or step-by-step (confirm each time)."
        ),
        "runnable_steps": pipeline_runner.list_runnable_steps(),
        "auto_run": False,
    }


@app.delete("/api/ingest/{batch_id}")
def ingest_delete(batch_id: str) -> dict:
    """Delete an upload batch directory (inputs + any batch output/)."""
    bid = (batch_id or "").strip()
    if not bid or any(ch in bid for ch in ("/", "\\", "..")) or bid in (".", ".."):
        raise HTTPException(400, "Invalid batch id")
    root = UPLOADS_DIR.resolve()
    dest = (UPLOADS_DIR / bid).resolve()
    try:
        dest.relative_to(root)
    except ValueError as e:
        raise HTTPException(400, "Invalid batch path") from e
    if dest == root or not dest.is_dir():
        raise HTTPException(404, f"Unknown batch: {bid}")
    try:
        shutil.rmtree(dest)
    except OSError as e:
        raise HTTPException(500, f"Could not delete batch: {e}") from e
    drop_catalog(upload_project_id(bid))
    # Keep pipeline jobs/logs — only Clear logs removes them.
    return {
        "ok": True,
        "batch_id": bid,
        "project_id": upload_project_id(bid),
        "message": f"Deleted upload batch {bid}",
    }


if UI_DIST.is_dir():
    assets = UI_DIST / "assets"
    if assets.is_dir():
        app.mount("/assets", StaticFiles(directory=str(assets)), name="ui-assets")
elif ASSETS_DIR.is_dir():
    app.mount("/assets", StaticFiles(directory=str(ASSETS_DIR)), name="assets")


@app.get("/{full_path:path}", response_class=HTMLResponse)
def spa_fallback(full_path: str) -> HTMLResponse:
    """SPA deep-link fallback when serving the React production build."""
    if full_path.startswith("api/"):
        raise HTTPException(404, "Not found")
    spa = UI_DIST / "index.html"
    if not spa.is_file():
        raise HTTPException(404, "Not found")
    candidate = (UI_DIST / full_path).resolve()
    try:
        candidate.relative_to(UI_DIST.resolve())
    except ValueError as e:
        raise HTTPException(404, "Not found") from e
    if candidate.is_file():
        return FileResponse(candidate)
    return HTMLResponse(spa.read_text(encoding="utf-8"))
