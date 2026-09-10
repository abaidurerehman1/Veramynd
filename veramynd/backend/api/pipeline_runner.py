"""Run real Veramynd CLI pipeline stages from the backend API.

Jobs write under a batch ``uploads/<id>/output/`` tree or a project's
``output_dir``. Requires ``confirm=true`` on every start. Only one job
runs at a time.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import threading
import traceback
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from uuid import uuid4

from .layout import PARSER_ROOT, RUNS_DIR, UPLOADS_DIR, VERAMYND_ROOT
from .projects import (
    batch_id_from_project,
    get_project_config,
    upload_project_id,
)

# Frontend Complete / step runs: product cut is Recall@25 + activity coverage.
FRONTEND_JUDGE_SHORTLIST_K = 25
FRONTEND_JUDGE_LIMIT = 25

# Runnable steps (UI + API). retrieval includes rerank; judge includes escalate.
STEP_ORDER = (
    "parsing",
    "normalization",
    "embedding",
    "retrieval",
    "judge",
    "results",
)

STEP_META: dict[str, dict[str, str]] = {
    "parsing": {
        "name": "Parse (Stage-1 export)",
        "detail": "PDF + standards -> stage1 lessons / standards.json",
    },
    "normalization": {
        "name": "Normalize",
        "detail": "Lessons + standards leaves (OpenAI)",
    },
    "embedding": {
        "name": "Embed standards",
        "detail": "Standards -> Qdrant veramynd_standards",
    },
    "retrieval": {
        "name": "Retrieve + rerank",
        "detail": "Hybrid dense + BM25 + RRF + CE → top 25 shortlist",
    },
    "judge": {
        "name": "Judge + escalation",
        "detail": "Top 25 + coverage; one batch call/lesson (Anthropic)",
    },
    "results": {
        "name": "Final report",
        "detail": "Alignments CSV + client correlation (DOCX/XLSX)",
    },
}


@dataclass
class PipelineJob:
    id: str
    mode: str  # full | step
    steps: list[str]
    status: str  # queued | running | succeeded | failed | cancelled
    created_at: str
    updated_at: str
    confirm: bool = True
    batch_id: str | None = None
    project_id: str | None = None
    framework: str = ""
    output_dir: str = ""
    current_step: str | None = None
    completed_steps: list[str] = field(default_factory=list)
    exit_code: int | None = None
    error: str | None = None
    log_path: str = ""
    message: str = ""
    # Soft progress within the active step (0-100); bumps on log lines.
    step_pct: int = 0
    # Estimated USD cost by runnable step id (from CLI usage lines / artifacts).
    stage_costs: dict[str, float] = field(default_factory=dict)
    total_cost_usd: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data.update(job_progress(self))
        return data


# (type_id, label, regex) — first match wins for a log line.
_ERROR_PATTERNS: tuple[tuple[str, str, str], ...] = (
    ("api_key", "API key / auth", r"api.?key|OPENAI_API_KEY|ANTHROPIC_API_KEY|authentication|unauthorized|401\b"),
    ("rate_limit", "Rate limit", r"rate.?limit|429\b|too many requests|quota"),
    ("qdrant", "Qdrant / vector DB", r"qdrant|connection refused|6333"),
    ("missing_artifact", "Missing artifact", r"missing|not found|no such file|does not exist"),
    ("validation", "Validation / trust gate", r"\bBLOCK\b|verification fail|trust.?gate|hard check"),
    ("timeout", "Timeout", r"timed? ?out|timeout"),
    ("llm", "LLM / model", r"LlmError|JudgeError|RetrieveError|EmbedError|finish_reason|anthropic|openai"),
    ("traceback", "Python traceback", r"Traceback \(most recent call last\)"),
    ("error", "Error", r"^ERROR:|\bERROR\b|Exception:|failed with|exited with code"),
    ("warning", "Warning", r"\bWARN(ING)?\b|deprecated"),
)


def classify_log_line(line: str) -> str | None:
    text = (line or "").strip()
    if not text:
        return None
    for type_id, _label, pattern in _ERROR_PATTERNS:
        if re.search(pattern, text, flags=re.IGNORECASE):
            return type_id
    return None


def error_type_labels() -> dict[str, str]:
    return {tid: label for tid, label, _ in _ERROR_PATTERNS}


def job_progress(job: PipelineJob) -> dict[str, Any]:
    """Overall % and per-step status for live UI."""
    steps = list(job.steps) or list(STEP_ORDER)
    total = max(1, len(steps))
    completed = [s for s in job.completed_steps if s in steps]
    n_done = len(completed)
    stage_rows: list[dict[str, Any]] = []
    for sid in steps:
        meta = STEP_META.get(sid, {"name": sid, "detail": ""})
        if sid in completed:
            st, sp = "complete", 100
        elif job.current_step == sid and job.status == "failed":
            st, sp = "failed", int(job.step_pct or 0)
        elif job.current_step == sid and job.status in ("running", "queued"):
            st, sp = "running", max(5, min(95, int(job.step_pct or 15)))
        elif job.status == "failed" and sid not in completed:
            st, sp = "pending", 0
        else:
            st, sp = "pending", 0
        stage_rows.append(
            {
                "id": sid,
                "name": meta["name"],
                "detail": meta["detail"],
                "status": st,
                "percent": sp,
            }
        )

    if job.status == "succeeded":
        percent = 100
    elif job.status == "queued":
        percent = 0
    else:
        # Completed steps + fraction of current
        cur = 0.0
        if job.current_step and job.current_step in steps and job.current_step not in completed:
            cur = max(0.05, min(0.95, (job.step_pct or 15) / 100.0))
        percent = int(min(99 if job.status == "running" else 100, 100 * (n_done + cur) / total))
        if job.status == "failed":
            percent = int(min(100, 100 * (n_done + cur) / total))

    return {
        "percent": percent,
        "stage_progress": stage_rows,
        "steps_total": total,
        "steps_done": n_done,
    }


def enrich_jobs(jobs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Ensure older persisted jobs still expose progress fields."""
    out: list[dict[str, Any]] = []
    for row in jobs:
        if "percent" in row and "stage_progress" in row:
            out.append(row)
            continue
        try:
            job = PipelineJob(**{k: row[k] for k in PipelineJob.__dataclass_fields__ if k in row})
            out.append(job.to_dict())
        except TypeError:
            out.append(row)
    return out


_lock = threading.Lock()
_jobs: dict[str, PipelineJob] = {}
_active_job_id: str | None = None
_worker: threading.Thread | None = None


def list_runnable_steps() -> list[dict[str, str]]:
    return [
        {"id": sid, "name": STEP_META[sid]["name"], "detail": STEP_META[sid]["detail"]}
        for sid in STEP_ORDER
    ]


def artifact_completed_steps(output_root: Path | str | None) -> list[str]:
    """Runnable step ids already satisfied by output folders (prefix-ordered).

    A step counts as done only when its artifacts look complete for every Stage-1
    lesson (not merely "some files exist"), so a mid-Normalize crash still leaves
    Normalize as the next step to resume.
    """
    if not output_root:
        return []
    root = Path(output_root)
    p = _paths(root)

    def json_stems(path: Path) -> set[str]:
        if not path.is_dir():
            return set()
        return {f.stem for f in path.glob("*.json") if f.is_file()}

    def has_files(path: Path, pattern: str = "*") -> bool:
        return path.is_dir() and any(x.is_file() for x in path.glob(pattern))

    lessons = json_stems(p["lessons"])
    done: list[str] = []
    if not lessons:
        return done
    done.append("parsing")

    # normalize_progress is a cache/progress sidecar, not a lesson
    norm = json_stems(p["normalize"]) - {"normalize_progress"}
    if lessons <= norm and has_files(p["normalize_standards"], "*.json"):
        done.append("normalization")
    else:
        return done

    if has_files(p["embeddings"]):
        done.append("embedding")
    else:
        return done

    retrieve = json_stems(p["retrieve"])
    if lessons <= retrieve and _retrieve_matches_frontend_k(p["retrieve"], lessons):
        done.append("retrieval")
    else:
        return done

    judge = json_stems(p["judge"])
    # Ignore *.incomplete.json stems — json_stems already is only *.json; incomplete
    # files are named *.incomplete.json so stem ends with .incomplete — filter those.
    judge_ok = {
        s
        for s in judge
        if not s.endswith(".incomplete") and (p["judge"] / f"{s}.json").is_file()
    }
    if lessons <= judge_ok and _judge_matches_frontend_cut(p["judge"], lessons):
        done.append("judge")
    else:
        return done

    # Results = alignments report AND client-format package (Exports downloads).
    # Must be newer than judge so a 50→25 re-judge still regenerates exports.
    if (
        p["report_csv"].is_file()
        and _has_client_format(p["reports"])
        and _results_fresh_vs_judge(p)
    ):
        done.append("results")
    return done


_recovered_jobs = False


def recover_interrupted_jobs() -> int:
    """Mark orphaned queued/running jobs as cancelled after process/machine stop.

    Pipeline workers are in-process threads — a power-off or API restart leaves
    stale ``running`` rows that would otherwise block new starts. Cleared jobs
    stay in Logging; re-run Complete auto / next step to resume from disk.
    """
    global _recovered_jobs, _active_job_id
    if _recovered_jobs:
        return 0
    _recovered_jobs = True
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    n = 0
    with _lock:
        _active_job_id = None
    for path in sorted(RUNS_DIR.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if data.get("status") not in ("queued", "running"):
            continue
        data["status"] = "cancelled"
        data["error"] = "interrupted"
        data["message"] = (
            "Interrupted (server or machine stopped). "
            "Re-run Complete auto or the next step — finished stages are skipped from saved output."
        )
        data["updated_at"] = _now()
        data["current_step"] = data.get("current_step")
        try:
            path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
            n += 1
            jid = str(data.get("id") or path.stem)
            with _lock:
                if jid in _jobs:
                    job = _jobs[jid]
                    job.status = "cancelled"
                    job.error = "interrupted"
                    job.message = data["message"]
                    job.updated_at = data["updated_at"]
        except OSError:
            continue
    return n


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _persist(job: PipelineJob) -> None:
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    path = RUNS_DIR / f"{job.id}.json"
    path.write_text(json.dumps(job.to_dict(), indent=2) + "\n", encoding="utf-8")


def _append_log(job: PipelineJob, line: str) -> None:
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    log = Path(job.log_path)
    with log.open("a", encoding="utf-8") as f:
        f.write(line)
        if not line.endswith("\n"):
            f.write("\n")


def get_job(job_id: str) -> PipelineJob | None:
    with _lock:
        job = _jobs.get(job_id)
        if job:
            return job
    path = RUNS_DIR / f"{job_id}.json"
    if not path.is_file():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    job = PipelineJob(**{k: data[k] for k in PipelineJob.__dataclass_fields__ if k in data})
    with _lock:
        _jobs[job_id] = job
    return job


def list_jobs(limit: int = 20) -> list[dict[str, Any]]:
    recover_interrupted_jobs()
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    rows: list[PipelineJob] = []
    seen: set[str] = set()
    with _lock:
        for j in _jobs.values():
            rows.append(j)
            seen.add(j.id)
    for path in sorted(RUNS_DIR.glob("*.json"), reverse=True):
        if path.stem in seen:
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            rows.append(
                PipelineJob(**{k: data[k] for k in PipelineJob.__dataclass_fields__ if k in data})
            )
        except (OSError, json.JSONDecodeError, TypeError):
            continue
    rows.sort(key=lambda j: j.created_at, reverse=True)
    return enrich_jobs([j.to_dict() for j in rows[:limit]])


def _unlink_job_files(job_id: str, log_path: str = "") -> None:
    json_path = RUNS_DIR / f"{job_id}.json"
    if json_path.is_file():
        try:
            json_path.unlink()
        except OSError:
            pass
    for candidate in (
        Path(log_path) if log_path else None,
        RUNS_DIR / f"{job_id}.log",
    ):
        if candidate is None:
            continue
        try:
            if candidate.is_file():
                candidate.unlink()
        except OSError:
            pass


def delete_jobs_for_project(
    *,
    project_id: str | None = None,
    batch_id: str | None = None,
) -> dict[str, Any]:
    """Remove persisted pipeline jobs/logs for a deleted project or upload batch."""
    pid = (project_id or "").strip() or None
    bid = (batch_id or "").strip() or None
    if not pid and not bid:
        return {"ok": True, "deleted": 0}

    deleted = 0
    global _active_job_id

    with _lock:
        to_drop = [
            j
            for j in list(_jobs.values())
            if (pid and j.project_id == pid) or (bid and j.batch_id == bid)
        ]
        for j in to_drop:
            _jobs.pop(j.id, None)
            if _active_job_id == j.id:
                _active_job_id = None
            _unlink_job_files(j.id, j.log_path)
            deleted += 1

    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    for path in list(RUNS_DIR.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        jp = str(data.get("project_id") or "") or None
        jb = str(data.get("batch_id") or "") or None
        if (pid and jp == pid) or (bid and jb == bid):
            jid = str(data.get("id") or path.stem)
            _unlink_job_files(jid, str(data.get("log_path") or ""))
            deleted += 1

    return {"ok": True, "deleted": deleted, "project_id": pid, "batch_id": bid}


def clear_all_jobs() -> dict[str, Any]:
    """Delete all pipeline job JSON + log files under ``backend/runs/``."""
    global _active_job_id
    deleted = 0
    with _lock:
        ids = list(_jobs.keys())
        for jid in ids:
            job = _jobs.pop(jid, None)
            _unlink_job_files(jid, job.log_path if job else "")
            deleted += 1
        _active_job_id = None

    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    for path in list(RUNS_DIR.glob("*.json")) + list(RUNS_DIR.glob("*.log")):
        try:
            path.unlink()
            deleted += 1
        except OSError:
            continue
    return {"ok": True, "deleted": deleted}


def job_log_tail(job_id: str, max_chars: int = 80_000) -> str:
    job = get_job(job_id)
    if not job or not job.log_path:
        return ""
    path = Path(job.log_path)
    if not path.is_file():
        return ""
    text = path.read_text(encoding="utf-8", errors="replace")
    if len(text) <= max_chars:
        return text
    return text[-max_chars:]


def job_log_full(job_id: str, max_chars: int = 500_000) -> str:
    return job_log_tail(job_id, max_chars=max_chars)


_STEP_HDR_RE = re.compile(r"^=== STEP (?P<step>[a-z_]+):\s*(?P<label>.*?)(?:\s*===)?\s*$", re.I)
_SKIP_HDR_RE = re.compile(
    r"^=== SKIP (?P<step>[a-z_]+):\s*(?P<label>.*?)(?:\s*\(already complete\))?\s*(?:===)?\s*$",
    re.I,
)
_COST_EST_RE = re.compile(r"Estimated total cost:\s*\$?\s*([0-9]+(?:\.[0-9]+)?)", re.I)
_COST_MACHINE_RE = re.compile(
    r"^COST\s+stage=(?P<stage>[a-z_]+)\s+estimated_usd=(?P<usd>[0-9]+(?:\.[0-9]+)?)\s*$",
    re.I,
)
_COST_TOTAL_RE = re.compile(
    r"^COST_TOTAL\s+estimated_usd=(?P<usd>[0-9]+(?:\.[0-9]+)?)\s*$",
    re.I,
)
_LESSON_PROG_RE = re.compile(
    r"^\[(?P<i>\d+)/(?P<n>\d+)\]\s+"
    r"(?:(?P<skip>SKIP)\s+)?"
    r"(?P<action>retrieve|judge|normalize|embed)?\s*"
    r"(?P<code>[A-Za-z][A-Za-z0-9_-]*(?:\.[A-Za-z0-9_-]+)*)"
    r"(?P<rest>.*)$",
    re.I,
)
_LESSON_ERR_RE = re.compile(
    r"^(?:ERROR(?:\s+on)?|WARNING:)\s+(?P<code>[A-Za-z][A-Za-z0-9._-]*)\s*[:\-]\s*(?P<rest>.*)$",
    re.I,
)
_BATCH_ALIGN_RE = re.compile(r"^Batch aligning (?P<n>\d+) lessons", re.I)


def _log_line_count(job: PipelineJob) -> int:
    path = Path(job.log_path) if job.log_path else RUNS_DIR / f"{job.id}.log"
    if not path.is_file():
        return 0
    try:
        return sum(1 for _ in path.open("r", encoding="utf-8", errors="replace"))
    except OSError:
        return 0


def _parse_cost_from_lines(lines: list[str]) -> float:
    """Best estimated USD from a log slice (prefers machine COST lines)."""
    machine = 0.0
    found_machine = False
    est = 0.0
    for line in lines:
        m = _COST_MACHINE_RE.match(line.strip())
        if m:
            machine += float(m.group("usd"))
            found_machine = True
            continue
        em = _COST_EST_RE.search(line)
        if em:
            est = float(em.group(1))
    if found_machine:
        return round(machine, 6)
    return round(est, 6)


def _sum_judge_artifact_cost(output_root: Path) -> float:
    judge_dir = output_root / "judge"
    if not judge_dir.is_dir():
        return 0.0
    total = 0.0
    for path in judge_dir.glob("*.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        usage = data.get("usage") if isinstance(data, dict) else None
        if isinstance(usage, dict) and usage.get("estimated_cost_usd") is not None:
            try:
                total += float(usage["estimated_cost_usd"])
            except (TypeError, ValueError):
                continue
    return round(total, 6)


def _emit_stage_cost(
    job: PipelineJob,
    step: str,
    *,
    output_root: Path,
    log_from_line: int,
    skipped: bool = False,
) -> float:
    """Append COST lines for a finished/skipped stage and update job.stage_costs."""
    if skipped:
        usd = 0.0
        note = "skipped (already complete)"
    else:
        path = Path(job.log_path) if job.log_path else RUNS_DIR / f"{job.id}.log"
        lines: list[str] = []
        if path.is_file():
            try:
                all_lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
                lines = all_lines[max(0, log_from_line) :]
            except OSError:
                lines = []
        usd = _parse_cost_from_lines(lines)
        if step == "judge" and usd <= 0:
            usd = _sum_judge_artifact_cost(output_root)
        note = "from CLI usage" if usd > 0 else "no billable API usage recorded"
    job.stage_costs[step] = usd
    job.total_cost_usd = round(sum(job.stage_costs.values()), 6)
    name = STEP_META.get(step, {}).get("name", step)
    _append_log(job, f"COST stage={step} estimated_usd={usd:.6f}")
    _append_log(job, f"Stage cost ({name}): ${usd:.4f} — {note}")
    _persist(job)
    return usd


def _emit_total_cost(job: PipelineJob) -> None:
    total = round(sum(float(v) for v in job.stage_costs.values()), 6)
    job.total_cost_usd = total
    _append_log(job, f"COST_TOTAL estimated_usd={total:.6f}")
    _append_log(job, f"Pipeline total estimated cost: ${total:.4f}")
    _persist(job)


def _entry_base(job: dict[str, Any], jid: str, line_no: int, line: str) -> dict[str, Any]:
    return {
        "job_id": jid,
        "line_no": line_no,
        "message": line[:2000],
        "job_status": job.get("status"),
        "mode": job.get("mode"),
        "project_id": job.get("project_id"),
        "batch_id": job.get("batch_id"),
        "created_at": job.get("created_at"),
        "stage_id": None,
        "stage_name": None,
        "lesson_code": None,
        "lesson_index": None,
        "lesson_total": None,
        "action": None,
    }


def analyze_job_logs(job_id: str | None = None, *, limit_jobs: int = 30) -> dict[str, Any]:
    """Parse job logs into typed entries + stage/lesson timeline for Logging."""
    jobs = list_jobs(limit=limit_jobs)
    if job_id:
        jobs = [j for j in jobs if j.get("id") == job_id]
        if not jobs:
            j = get_job(job_id)
            jobs = [j.to_dict()] if j else []

    entries: list[dict[str, Any]] = []
    by_type: dict[str, list[dict[str, Any]]] = {tid: [] for tid, _, _ in _ERROR_PATTERNS}
    by_type["info"] = []
    by_type["stage"] = []
    by_type["lesson"] = []
    by_type["cost"] = []

    stages_out: list[dict[str, Any]] = []
    job_cost_rows: list[dict[str, Any]] = []

    for job in jobs:
        jid = str(job.get("id") or "")
        text = job_log_full(jid) if jid else ""
        current_stage: str | None = None
        current_label = ""
        stage_lessons: dict[str, dict[str, Any]] = {}
        stage_rows: list[dict[str, Any]] = []
        stage_cost_map: dict[str, float] = {}
        for raw_line in text.splitlines():
            cm = _COST_MACHINE_RE.match(raw_line.strip())
            if cm:
                stage_cost_map[cm.group("stage").lower()] = float(cm.group("usd"))
        total_from_log = None
        for raw_line in text.splitlines():
            tm = _COST_TOTAL_RE.match(raw_line.strip())
            if tm:
                total_from_log = float(tm.group("usd"))
        if not stage_cost_map and isinstance(job.get("stage_costs"), dict):
            stage_cost_map = {
                str(k): float(v)
                for k, v in job["stage_costs"].items()
                if v is not None
            }
        job_total = (
            total_from_log
            if total_from_log is not None
            else float(job.get("total_cost_usd") or 0)
            or round(sum(stage_cost_map.values()), 6)
        )
        job_cost_rows.append(
            {
                "job_id": jid,
                "total_cost_usd": job_total,
                "stage_costs": stage_cost_map,
                "status": job.get("status"),
                "mode": job.get("mode"),
            }
        )

        def flush_stage() -> None:
            nonlocal stage_lessons, stage_rows, current_stage, current_label
            if not current_stage:
                return
            lessons = list(stage_lessons.values())
            ok = sum(1 for L in lessons if L.get("status") in ("ok", "done"))
            skip = sum(1 for L in lessons if L.get("status") == "skip")
            err = sum(1 for L in lessons if L.get("status") == "error")
            running = sum(1 for L in lessons if L.get("status") == "running")
            stage_rows.append(
                {
                    "job_id": jid,
                    "stage_id": current_stage,
                    "stage_name": current_label
                    or STEP_META.get(current_stage, {}).get("name", current_stage),
                    "status": (
                        "failed"
                        if err
                        else "running"
                        if running or (job.get("status") == "running" and job.get("current_step") == current_stage)
                        else "complete"
                        if lessons or current_stage in (job.get("completed_steps") or [])
                        else "started"
                    ),
                    "lessons": lessons,
                    "lesson_count": len(lessons),
                    "ok": ok,
                    "skip": skip,
                    "error": err,
                    "running": running,
                    "cost_usd": stage_cost_map.get(current_stage),
                }
            )
            stage_lessons = {}

        for i, raw in enumerate(text.splitlines()):
            line = raw.rstrip()
            if not line.strip():
                continue

            base = _entry_base(job, jid, i + 1, line)
            etype = classify_log_line(line)

            step_m = _STEP_HDR_RE.match(line.strip()) or _SKIP_HDR_RE.match(line.strip())
            if step_m:
                flush_stage()
                current_stage = step_m.group("step").lower()
                current_label = (step_m.group("label") or "").strip(" =")
                etype = "stage"
                base.update(
                    {
                        "type": "stage",
                        "type_label": "Stage",
                        "stage_id": current_stage,
                        "stage_name": current_label
                        or STEP_META.get(current_stage, {}).get("name", current_stage),
                    }
                )
                entries.append(base)
                by_type["stage"].append(base)
                continue

            cost_m = _COST_MACHINE_RE.match(line.strip()) or _COST_TOTAL_RE.match(line.strip())
            if cost_m or _COST_EST_RE.search(line) or line.startswith("Stage cost (") or line.startswith(
                "Pipeline total estimated cost:"
            ):
                etype = "cost"
                base.update(
                    {
                        "type": "cost",
                        "type_label": "Cost",
                        "stage_id": current_stage,
                        "stage_name": current_label
                        or (
                            STEP_META.get(current_stage or "", {}).get("name")
                            if current_stage
                            else None
                        ),
                    }
                )
                entries.append(base)
                by_type.setdefault("cost", []).append(base)
                continue

            batch_m = _BATCH_ALIGN_RE.match(line.strip())
            if batch_m:
                etype = etype or "info"
                base.update(
                    {
                        "type": etype,
                        "type_label": (
                            error_type_labels().get(etype, etype)
                            if etype != "info"
                            else "Info / step markers"
                        ),
                        "stage_id": current_stage,
                        "stage_name": current_label
                        or (
                            STEP_META.get(current_stage or "", {}).get("name")
                            if current_stage
                            else None
                        ),
                        "lesson_total": int(batch_m.group("n")),
                    }
                )
                entries.append(base)
                by_type.setdefault(etype, []).append(base)
                continue

            lesson_m = _LESSON_PROG_RE.match(line.strip())
            err_m = None if lesson_m else _LESSON_ERR_RE.match(line.strip())

            if lesson_m or err_m:
                if lesson_m:
                    code = lesson_m.group("code")
                    action = (lesson_m.group("action") or "").lower() or None
                    idx = int(lesson_m.group("i"))
                    total = int(lesson_m.group("n"))
                    rest = (lesson_m.group("rest") or "").strip()
                    skipped = bool(lesson_m.group("skip"))
                    if skipped:
                        status = "skip"
                    elif re.search(r"\berror\b|failed", rest, re.I):
                        status = "error"
                    elif re.search(r"\bdone\b|\bok\b", rest, re.I) or rest.endswith("..."):
                        # trailing ... usually means started; done/ok means finished
                        status = "done" if re.search(r"\bdone\b|\bok\b", rest, re.I) else "running"
                    elif "queued" in rest.lower():
                        status = "running"
                    else:
                        status = "ok" if not rest or rest in {".", ".."} else "running"
                        if rest.endswith("...") or rest.endswith("…"):
                            status = "running"
                else:
                    assert err_m is not None
                    code = err_m.group("code")
                    action = None
                    idx = None
                    total = None
                    rest = (err_m.group("rest") or "").strip()
                    status = "error" if line.upper().startswith("ERROR") else "warning"
                    if status == "warning":
                        status = "ok"  # keep as lesson note; type stays warning below

                # Infer stage from action if header missing
                if not current_stage and action:
                    current_stage = {
                        "retrieve": "retrieval",
                        "judge": "judge",
                        "normalize": "normalization",
                        "embed": "embedding",
                    }.get(action, current_stage)

                stage_name = current_label or (
                    STEP_META.get(current_stage or "", {}).get("name") if current_stage else None
                )

                prev = stage_lessons.get(code)
                lesson_row = {
                    "code": code,
                    "action": action or (prev or {}).get("action"),
                    "index": idx if idx is not None else (prev or {}).get("index"),
                    "total": total if total is not None else (prev or {}).get("total"),
                    "status": status,
                    "message": line[:500],
                    "line_no": i + 1,
                }
                rank = {"running": 0, "ok": 1, "done": 2, "skip": 2, "error": 3}
                if prev and rank.get(str(prev.get("status")), 0) > rank.get(status, 0):
                    lesson_row["status"] = prev["status"]
                    if not action:
                        lesson_row["action"] = prev.get("action")
                stage_lessons[code] = {**(prev or {}), **lesson_row}

                row_type = "lesson" if status != "error" else (etype or "error")
                if status == "error" and etype in (None, "error"):
                    row_type = "error"
                elif status != "error":
                    row_type = "lesson"
                    if etype == "warning":
                        row_type = "warning"

                base.update(
                    {
                        "type": row_type,
                        "type_label": (
                            "Lesson"
                            if row_type == "lesson"
                            else error_type_labels().get(row_type, row_type)
                        ),
                        "stage_id": current_stage,
                        "stage_name": stage_name,
                        "lesson_code": code,
                        "lesson_index": idx,
                        "lesson_total": total,
                        "action": action,
                    }
                )
                entries.append(base)
                by_type.setdefault(row_type, []).append(base)
                continue

            # Generic headers / errors
            is_header = (
                line.startswith("$ ")
                or line.startswith("Workspace:")
                or line.startswith("PDF:")
                or line.startswith("XLSX:")
                or line.startswith("Output:")
                or line.startswith("Steps:")
            )
            if etype is None and not is_header:
                continue
            if etype is None:
                etype = "info"
            base.update(
                {
                    "type": etype,
                    "type_label": (
                        "Info / step markers"
                        if etype == "info"
                        else error_type_labels().get(etype, etype)
                    ),
                    "stage_id": current_stage,
                    "stage_name": current_label
                    or (
                        STEP_META.get(current_stage or "", {}).get("name")
                        if current_stage
                        else None
                    ),
                }
            )
            entries.append(base)
            by_type.setdefault(etype, []).append(base)

        flush_stage()
        stages_out.extend(stage_rows)

    counts = {k: len(v) for k, v in by_type.items() if v}
    grand_total = round(sum(float(r.get("total_cost_usd") or 0) for r in job_cost_rows), 6)
    return {
        "jobs": enrich_jobs(jobs),
        "entries": entries,
        "stages": stages_out,
        "job_costs": job_cost_rows,
        "total_cost_usd": grand_total,
        "by_type": {k: v for k, v in by_type.items() if v},
        "counts": counts,
        "type_labels": {
            **error_type_labels(),
            "info": "Info / step markers",
            "stage": "Stage",
            "lesson": "Lesson",
            "cost": "Cost",
        },
    }


def active_job() -> PipelineJob | None:
    with _lock:
        if not _active_job_id:
            return None
        job = _jobs.get(_active_job_id)
        if job and job.status in ("queued", "running"):
            return job
    # Fall back to newest running from disk
    for row in list_jobs(limit=5):
        if row.get("status") in ("queued", "running"):
            return get_job(str(row["id"]))
    return None


def _find_upload_file(batch_dir: Path, exts: tuple[str, ...]) -> Path | None:
    for p in sorted(batch_dir.iterdir()):
        if p.is_file() and p.suffix.lower() in exts:
            return p
    return None


def _resolve_workspace(
    *,
    batch_id: str | None,
    project_id: str | None,
    framework: str,
) -> tuple[Path, Path, Path, str, str]:
    """Return (guide_pdf, standards_xlsx, output_root, framework, label)."""
    if batch_id:
        batch_dir = UPLOADS_DIR / batch_id
        if not batch_dir.is_dir():
            raise ValueError(f"Unknown upload batch: {batch_id}")
        pdf = _find_upload_file(batch_dir, (".pdf",))
        xlsx = _find_upload_file(batch_dir, (".xlsx", ".xlsm"))
        if not pdf:
            raise ValueError("Batch has no curriculum PDF")
        if not xlsx:
            raise ValueError("Batch has no standards XLSX")
        meta_path = batch_dir / "meta.json"
        fw = framework
        if not fw and meta_path.is_file():
            try:
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
                fw = str(meta.get("framework") or "") or "GA ELA"
            except (OSError, json.JSONDecodeError):
                fw = "GA ELA"
        if not fw:
            fw = "GA ELA"
        out = batch_dir / "output"
        out.mkdir(parents=True, exist_ok=True)
        return pdf, xlsx, out, fw, f"batch:{batch_id}"

    if project_id:
        cfg = get_project_config(project_id)
        if not cfg.guide_pdf.is_file():
            raise ValueError(f"Project guide PDF missing: {cfg.guide_pdf}")
        if not cfg.standards_xlsx.is_file():
            raise ValueError(f"Project standards XLSX missing: {cfg.standards_xlsx}")
        fw = framework or cfg.framework or "GA ELA"
        cfg.output_dir.mkdir(parents=True, exist_ok=True)
        return cfg.guide_pdf, cfg.standards_xlsx, cfg.output_dir, fw, f"project:{project_id}"

    raise ValueError("Provide batch_id or project_id")


def _cli_env() -> dict[str, str]:
    env = dict(os.environ)
    # Package lives under veramynd_parser/
    pp = str(PARSER_ROOT)
    prev = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = pp if not prev else f"{pp}{os.pathsep}{prev}"
    # Load .env if present (normalize/judge keys)
    dotenv = PARSER_ROOT / ".env"
    if dotenv.is_file():
        for line in dotenv.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            k, v = k.strip(), v.strip().strip('"').strip("'")
            if k and k not in env:
                env[k] = v
    return env


def _run_cmd(job: PipelineJob, argv: list[str], *, cwd: Path | None = None) -> int:
    import time

    _append_log(job, f"\n$ {' '.join(argv)}\n")
    proc = subprocess.Popen(
        argv,
        cwd=str(cwd or PARSER_ROOT),
        env=_cli_env(),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    assert proc.stdout is not None
    last_persist = 0.0
    n_lines = 0
    for line in proc.stdout:
        _append_log(job, line.rstrip("\n"))
        n_lines += 1
        # Soft in-step progress: asymptote toward 90% while logs stream
        job.step_pct = min(90, 10 + int(80 * (1 - pow(0.985, n_lines))))
        job.updated_at = _now()
        now = time.time()
        if now - last_persist >= 0.75:
            _persist(job)
            last_persist = now
    _persist(job)
    return proc.wait()


def _py_mod(*args: str) -> list[str]:
    return [sys.executable, "-m", *args]


def _paths(output_root: Path) -> dict[str, Path]:
    return {
        "stage1": output_root / "stage1",
        "lessons": output_root / "stage1" / "lessons",
        "standards_json": output_root / "stage1" / "standards.json",
        "normalize": output_root / "normalize",
        "normalize_standards": output_root / "normalize_standards",
        "embeddings": output_root / "embeddings",
        "retrieve": output_root / "retrieve",
        "judge": output_root / "judge",
        "reports": output_root / "reports",
        "report_csv": output_root / "reports" / "alignments_all.csv",
        "client_docx": output_root / "reports" / "client_correlation.docx",
        "client_xlsx": output_root / "reports" / "client_correlation.xlsx",
        "client_summary": output_root
        / "reports"
        / "client_correlation.summary.json",
    }


def _has_client_format(reports: Path) -> bool:
    """True when client correlation DOCX exists (default or registry naming)."""
    if not reports.is_dir():
        return False
    if (reports / "client_correlation.docx").is_file():
        return True
    return any(reports.glob("*client_correlation*.docx"))


def _latest_mtime(paths: list[Path]) -> float:
    latest = 0.0
    for path in paths:
        try:
            if path.is_file():
                latest = max(latest, path.stat().st_mtime)
        except OSError:
            continue
    return latest


def _results_fresh_vs_judge(paths: dict[str, Path]) -> bool:
    """Report + client package must not be older than the newest judge JSON."""
    judge_dir = paths["judge"]
    if not judge_dir.is_dir():
        return False
    judge_files = [
        f
        for f in judge_dir.glob("*.json")
        if f.is_file() and not f.name.endswith(".incomplete.json")
    ]
    if not judge_files:
        return False
    judge_mtime = _latest_mtime(judge_files)
    report_mtime = _latest_mtime([paths["report_csv"]])
    client_files = list(paths["reports"].glob("*client_correlation*.docx"))
    client_mtime = _latest_mtime(client_files)
    # Allow tiny FS timestamp skew.
    return report_mtime + 1.0 >= judge_mtime and client_mtime + 1.0 >= judge_mtime


def _read_json_obj(path: Path) -> dict[str, Any] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeError):
        return None
    return data if isinstance(data, dict) else None


def _retrieve_file_matches_frontend_k(path: Path) -> bool:
    data = _read_json_obj(path)
    if not data:
        return False
    k = data.get("judge_shortlist_k")
    if k is not None:
        try:
            return int(k) == FRONTEND_JUDGE_SHORTLIST_K
        except (TypeError, ValueError):
            return False
    n = len(data.get("candidates") or [])
    return n == FRONTEND_JUDGE_SHORTLIST_K


def _retrieve_matches_frontend_k(retrieve_dir: Path, lessons: set[str]) -> bool:
    if not lessons or not retrieve_dir.is_dir():
        return False
    for stem in lessons:
        path = retrieve_dir / f"{stem}.json"
        if not path.is_file() or not _retrieve_file_matches_frontend_k(path):
            return False
    return True


def _judge_file_matches_frontend_cut(path: Path) -> bool:
    """Accept judge JSON produced under top-25 (+ coverage extras ≤ 8)."""
    data = _read_json_obj(path)
    if not data:
        return False
    if data.get("judge_limit") is not None:
        try:
            return int(data["judge_limit"]) == FRONTEND_JUDGE_LIMIT
        except (TypeError, ValueError):
            return False
    # Legacy reports (no judge_limit): head ≈ candidate_count − coverage injects.
    try:
        n = int(data.get("candidate_count") or 0)
    except (TypeError, ValueError):
        n = len(data.get("verdicts") or [])
    injected = data.get("coverage_pass_injected") or []
    try:
        n_inj = len(injected)
    except TypeError:
        n_inj = 0
    head = max(0, n - n_inj)
    max_total = FRONTEND_JUDGE_LIMIT + 8  # MAX_COVERAGE_EXTRAS
    return head <= FRONTEND_JUDGE_LIMIT and n <= max_total


def _judge_matches_frontend_cut(judge_dir: Path, lessons: set[str]) -> bool:
    if not lessons or not judge_dir.is_dir():
        return False
    for stem in lessons:
        path = judge_dir / f"{stem}.json"
        if not path.is_file() or not _judge_file_matches_frontend_cut(path):
            return False
    return True


def _needs_force_retrieve(output_root: Path) -> bool:
    """True when some retrieve JSON exists but is not the frontend shortlist-k."""
    p = _paths(output_root)
    if not p["retrieve"].is_dir() or not p["lessons"].is_dir():
        return False
    lessons = {f.stem for f in p["lessons"].glob("*.json") if f.is_file()}
    for stem in lessons:
        path = p["retrieve"] / f"{stem}.json"
        if path.is_file() and not _retrieve_file_matches_frontend_k(path):
            return True
    return False


def _needs_force_judge(output_root: Path) -> bool:
    """True when some judge JSON exists but is not the frontend 25+coverage cut."""
    p = _paths(output_root)
    if not p["judge"].is_dir() or not p["lessons"].is_dir():
        return False
    lessons = {f.stem for f in p["lessons"].glob("*.json") if f.is_file()}
    for stem in lessons:
        path = p["judge"] / f"{stem}.json"
        if path.is_file() and not _judge_file_matches_frontend_cut(path):
            return True
    return False


def _job_project_id(job: PipelineJob) -> str | None:
    if job.project_id:
        return job.project_id
    if job.batch_id:
        return upload_project_id(job.batch_id)
    return None


def _client_output_paths(job: PipelineJob, output_root: Path) -> tuple[Path, Path, Path]:
    """DOCX / XLSX / summary paths that Exports already knows about."""
    p = _paths(output_root)
    pid = _job_project_id(job)
    if pid:
        try:
            cfg = get_project_config(pid)
        except KeyError:
            cfg = None
        if cfg is not None:
            docx = cfg.client_docx if cfg.client_docx else p["client_docx"]
            xlsx = cfg.client_xlsx if cfg.client_xlsx else p["client_xlsx"]
            # Package writes ``<docx_stem>.summary.json`` next to the DOCX.
            summary = docx.with_suffix(".summary.json")
            return docx, xlsx, summary
    return p["client_docx"], p["client_xlsx"], p["client_summary"]


def _client_format_labels(job: PipelineJob, framework: str) -> dict[str, str]:
    """Publisher-agnostic labels from upload meta / project config (no EL hardcodes)."""
    program_name = "Curriculum"
    guide_label = "Guide"
    grade_label = "Grade"
    framework_header = (framework or "").strip() or "Standards framework"
    standards_header = "Standards"

    meta: dict[str, Any] = {}
    if job.batch_id:
        meta_path = UPLOADS_DIR / job.batch_id / "meta.json"
        if meta_path.is_file():
            try:
                loaded = json.loads(meta_path.read_text(encoding="utf-8"))
                if isinstance(loaded, dict):
                    meta = loaded
            except (OSError, json.JSONDecodeError):
                meta = {}

    pid = _job_project_id(job)
    cfg = None
    if pid:
        try:
            cfg = get_project_config(pid)
        except KeyError:
            cfg = None

    if meta.get("program_name"):
        program_name = str(meta["program_name"]).strip() or program_name
    elif cfg and cfg.publisher:
        program_name = str(cfg.publisher).strip() or program_name
    elif cfg and cfg.name:
        program_name = str(cfg.name).strip() or program_name

    if meta.get("guide_label"):
        guide_label = str(meta["guide_label"]).strip() or guide_label
    elif cfg and cfg.module:
        guide_label = str(cfg.module).strip() or guide_label

    if meta.get("grade_label"):
        grade_label = str(meta["grade_label"]).strip() or grade_label
    elif cfg and cfg.grade is not None:
        grade_label = f"Grade {cfg.grade}"

    fw = (
        str(meta.get("framework") or "").strip()
        or (cfg.framework if cfg else "")
        or framework_header
    )
    framework_header = str(fw).strip() or framework_header
    standards_header = framework_header

    return {
        "program_name": program_name,
        "guide_label": guide_label,
        "grade_label": grade_label,
        "framework_header": framework_header,
        "standards_header": standards_header,
    }


StepFn = Callable[[PipelineJob, Path, Path, Path, str], int]


def _step_parsing(
    job: PipelineJob, pdf: Path, xlsx: Path, output_root: Path, framework: str
) -> int:
    p = _paths(output_root)
    argv = _py_mod(
        "veramynd_parser.cli",
        "export",
        str(pdf),
        "--out",
        str(p["stage1"]),
        "--standards",
        str(xlsx),
        "--framework",
        framework,
    )
    return _run_cmd(job, argv)


def _step_normalization(
    job: PipelineJob, pdf: Path, xlsx: Path, output_root: Path, framework: str
) -> int:
    del pdf, xlsx, framework
    p = _paths(output_root)
    if not p["lessons"].is_dir():
        _append_log(job, "ERROR: stage1/lessons missing — run parsing first")
        return 1
    code = _run_cmd(
        job,
        _py_mod(
            "veramynd_parser.cli",
            "normalize-lessons",
            str(p["lessons"]),
            "--out",
            str(p["normalize"]),
        ),
    )
    if code != 0:
        return code
    if not p["standards_json"].is_file():
        _append_log(job, "ERROR: stage1/standards.json missing")
        return 1
    return _run_cmd(
        job,
        _py_mod(
            "veramynd_parser.cli",
            "normalize-standards",
            str(p["standards_json"]),
            "--out",
            str(p["normalize_standards"]),
        ),
    )


def _step_embedding(
    job: PipelineJob, pdf: Path, xlsx: Path, output_root: Path, framework: str
) -> int:
    del pdf, xlsx, framework
    p = _paths(output_root)
    if not p["normalize_standards"].is_dir():
        _append_log(job, "ERROR: normalize_standards missing — run normalization first")
        return 1
    return _run_cmd(
        job,
        _py_mod(
            "veramynd_parser.cli",
            "embed-standards",
            str(p["normalize_standards"]),
            "--out",
            str(p["embeddings"]),
        ),
    )


def _batch_align(
    job: PipelineJob,
    output_root: Path,
    *,
    skip_retrieve: bool = False,
    skip_judge: bool = False,
    skip_report: bool = False,
    force_retrieve: bool = False,
    force_judge: bool = False,
) -> int:
    p = _paths(output_root)
    p["reports"].mkdir(parents=True, exist_ok=True)
    argv = _py_mod(
        "veramynd_parser.scripts.batch_align_all",
        "--lessons-dir",
        str(p["lessons"]),
        "--normalize-dir",
        str(p["normalize"]),
        "--standards-dir",
        str(p["normalize_standards"]),
        "--retrieve-dir",
        str(p["retrieve"]),
        "--judge-dir",
        str(p["judge"]),
        "--report-csv",
        str(p["report_csv"]),
        # Product cut: top-25 shortlist; one batch judge call per lesson + coverage.
        "--judge-shortlist-k",
        str(FRONTEND_JUDGE_SHORTLIST_K),
        "--judge-limit",
        str(FRONTEND_JUDGE_LIMIT),
        "--batch",
    )
    if skip_retrieve:
        argv.append("--skip-retrieve")
    if skip_judge:
        argv.append("--skip-judge")
    if skip_report:
        argv.append("--skip-report")
    if force_retrieve and not skip_retrieve:
        argv.append("--force-retrieve")
    if force_judge and not skip_judge:
        argv.append("--force-judge")
    if not skip_retrieve or not skip_judge:
        _append_log(
            job,
            f"Align config: shortlist_k={FRONTEND_JUDGE_SHORTLIST_K} "
            f"judge_limit={FRONTEND_JUDGE_LIMIT} coverage_pass=on judge_mode=batch"
            + (" force_retrieve" if force_retrieve and not skip_retrieve else "")
            + (" force_judge" if force_judge and not skip_judge else ""),
        )
    return _run_cmd(job, argv)


def _step_retrieval(
    job: PipelineJob, pdf: Path, xlsx: Path, output_root: Path, framework: str
) -> int:
    del pdf, xlsx, framework
    force = _needs_force_retrieve(output_root)
    if force:
        _append_log(
            job,
            f"Stale retrieve shortlist detected — re-running retrieve at "
            f"k={FRONTEND_JUDGE_SHORTLIST_K}",
        )
    return _batch_align(
        job,
        output_root,
        skip_judge=True,
        skip_report=True,
        force_retrieve=force,
    )


def _step_judge(
    job: PipelineJob, pdf: Path, xlsx: Path, output_root: Path, framework: str
) -> int:
    del pdf, xlsx, framework
    force = _needs_force_judge(output_root)
    if force:
        _append_log(
            job,
            f"Stale judge cut detected — re-running judge at "
            f"limit={FRONTEND_JUDGE_LIMIT} + coverage",
        )
    return _batch_align(
        job,
        output_root,
        skip_retrieve=True,
        skip_report=True,
        force_judge=force,
    )


def _write_client_correlation(
    job: PipelineJob, output_root: Path, framework: str
) -> int:
    """Build client DOCX/XLSX/summary for Exports (publisher-agnostic labels)."""
    p = _paths(output_root)
    if not p["standards_json"].is_file():
        _append_log(
            job,
            "ERROR: stage1/standards.json missing — cannot build client format",
        )
        return 1
    if not p["judge"].is_dir():
        _append_log(job, "ERROR: judge/ missing — cannot build client format")
        return 1
    judge_files = [
        f
        for f in p["judge"].glob("*.json")
        if f.is_file() and not f.name.endswith(".incomplete.json")
    ]
    if not judge_files:
        _append_log(job, "ERROR: no judge JSON files — cannot build client format")
        return 1

    docx, xlsx, summary = _client_output_paths(job, output_root)
    docx.parent.mkdir(parents=True, exist_ok=True)
    labels = _client_format_labels(job, framework)
    argv = _py_mod(
        "veramynd_parser.cli",
        "client-correlation",
        "--judge-dir",
        str(p["judge"]),
        "--standards",
        str(p["standards_json"]),
        "--out-docx",
        str(docx),
        "--out-xlsx",
        str(xlsx),
        "--program-name",
        labels["program_name"],
        "--guide-label",
        labels["guide_label"],
        "--grade-label",
        labels["grade_label"],
        "--framework-header",
        labels["framework_header"],
        "--standards-header",
        labels["standards_header"],
    )
    if p["lessons"].is_dir():
        argv.extend(["--lessons-dir", str(p["lessons"])])

    _append_log(
        job,
        f"Client format → {docx.name} / {xlsx.name} "
        f"(program={labels['program_name']!r}, guide={labels['guide_label']!r})",
    )
    code = _run_cmd(job, argv)
    if code != 0:
        return code

    # CLI success must still produce the files Exports lists.
    missing = [str(path) for path in (docx, xlsx, summary) if not path.is_file()]
    if missing:
        _append_log(
            job,
            "ERROR: client-correlation exited 0 but outputs missing:\n  "
            + "\n  ".join(missing),
        )
        return 1
    _append_log(job, f"Client format ready for Exports: {docx}")
    return 0


def _step_results(
    job: PipelineJob, pdf: Path, xlsx: Path, output_root: Path, framework: str
) -> int:
    del pdf, xlsx
    code = _batch_align(job, output_root, skip_retrieve=True, skip_judge=True)
    if code != 0:
        return code
    p = _paths(output_root)
    if not p["report_csv"].is_file():
        _append_log(
            job,
            f"ERROR: alignments report missing after results step: {p['report_csv']}",
        )
        return 1
    return _write_client_correlation(job, output_root, framework)


_STEP_FNS: dict[str, StepFn] = {
    "parsing": _step_parsing,
    "normalization": _step_normalization,
    "embedding": _step_embedding,
    "retrieval": _step_retrieval,
    "judge": _step_judge,
    "results": _step_results,
}


def _execute(job: PipelineJob) -> None:
    global _active_job_id
    try:
        pdf, xlsx, output_root, framework, label = _resolve_workspace(
            batch_id=job.batch_id,
            project_id=None if job.batch_id else job.project_id,
            framework=job.framework,
        )
        job.output_dir = str(output_root)
        job.status = "running"
        job.message = f"Running against {label}"
        job.updated_at = _now()
        _persist(job)
        _append_log(job, f"Workspace: {label}")
        _append_log(job, f"PDF: {pdf}")
        _append_log(job, f"XLSX: {xlsx}")
        _append_log(job, f"Output: {output_root}")
        _append_log(job, f"Steps: {', '.join(job.steps)}")

        already = set(artifact_completed_steps(output_root))
        if already:
            _append_log(
                job,
                "Resume: skipping completed stages → " + ", ".join(already),
            )
            for sid in job.steps:
                if sid in already and sid not in job.completed_steps:
                    job.completed_steps.append(sid)
            _persist(job)

        for step in job.steps:
            if step in already:
                job.current_step = step
                job.step_pct = 100
                job.updated_at = _now()
                _append_log(
                    job,
                    f"\n=== SKIP {step}: {STEP_META[step]['name']} (already complete) ===",
                )
                _emit_stage_cost(
                    job, step, output_root=output_root, log_from_line=0, skipped=True
                )
                continue

            job.current_step = step
            job.step_pct = 5
            job.updated_at = _now()
            _persist(job)
            _append_log(job, f"\n=== STEP {step}: {STEP_META[step]['name']} ===")
            log_at = _log_line_count(job)
            fn = _STEP_FNS[step]
            code = fn(job, pdf, xlsx, output_root, framework)
            _emit_stage_cost(
                job, step, output_root=output_root, log_from_line=log_at, skipped=False
            )
            if code != 0:
                job.exit_code = code
                job.status = "failed"
                job.error = f"Step {step} exited with code {code}"
                job.message = job.error
                job.updated_at = _now()
                _emit_total_cost(job)
                _persist(job)
                return
            job.step_pct = 100
            if step not in job.completed_steps:
                job.completed_steps.append(step)
            already.add(step)
            _persist(job)
            try:
                from .catalog import reload_catalog
                from .projects import upload_project_id

                if job.project_id:
                    reload_catalog(job.project_id)
                elif job.batch_id:
                    reload_catalog(upload_project_id(job.batch_id))
            except Exception:  # noqa: BLE001
                pass

        _emit_total_cost(job)
        job.exit_code = 0
        job.status = "succeeded"
        job.current_step = None
        job.step_pct = 100
        job.message = (
            f"Finished. Artifacts in {output_root}. "
            f"Estimated total cost ${job.total_cost_usd:.4f}. "
            "Open this upload in the project switcher. Overview is ready when judge output exists."
        )
        job.updated_at = _now()
        _persist(job)
        # Refresh Overview/Pipeline catalog for registry or upload projects
        try:
            from .catalog import reload_catalog
            from .projects import upload_project_id

            if job.project_id:
                reload_catalog(job.project_id)
            elif job.batch_id:
                reload_catalog(upload_project_id(job.batch_id))
        except Exception:  # noqa: BLE001
            _append_log(job, "Note: catalog reload after run failed (non-fatal)")
    except Exception as e:  # noqa: BLE001
        job.status = "failed"
        job.error = str(e)
        job.message = str(e)
        job.updated_at = _now()
        _append_log(job, traceback.format_exc())
        try:
            _emit_total_cost(job)
        except Exception:  # noqa: BLE001
            _persist(job)
        # Still try to refresh so Overview can show partial "running" artifacts
        try:
            from .catalog import reload_catalog
            from .projects import upload_project_id

            if job.project_id:
                reload_catalog(job.project_id)
            elif job.batch_id:
                reload_catalog(upload_project_id(job.batch_id))
        except Exception:  # noqa: BLE001
            pass
    finally:
        with _lock:
            if _active_job_id == job.id:
                _active_job_id = None


def start_job(
    *,
    mode: str,
    step: str | None = None,
    batch_id: str | None = None,
    project_id: str | None = None,
    framework: str = "",
    confirm: bool = False,
) -> PipelineJob:
    recover_interrupted_jobs()
    if not confirm:
        raise ValueError("confirm=true is required to start a pipeline run")
    if mode not in ("full", "step"):
        raise ValueError("mode must be 'full' or 'step'")
    if not batch_id and not project_id:
        raise ValueError("Provide batch_id (upload) or project_id")
    if batch_id and project_id:
        derived = upload_project_id(batch_id)
        if project_id != derived and batch_id_from_project(project_id) != batch_id:
            raise ValueError("batch_id and project_id refer to different workspaces")
    # Keep both ids on upload jobs so Overview / Logging / Pipeline match the same run
    if batch_id and not project_id:
        project_id = upload_project_id(batch_id)
    elif project_id and not batch_id:
        batch_id = batch_id_from_project(project_id)

    if mode == "full":
        steps = list(STEP_ORDER)
    else:
        if not step or step not in _STEP_FNS:
            raise ValueError(
                f"step must be one of: {', '.join(STEP_ORDER)}"
            )
        steps = [step]

    # Validate workspace early — prefer batch path when both ids present
    pdf, xlsx, output_root, fw, _label = _resolve_workspace(
        batch_id=batch_id,
        project_id=None if batch_id else project_id,
        framework=framework,
    )
    del pdf, xlsx

    already = artifact_completed_steps(output_root)
    if mode == "full" and already:
        # Keep full step list for progress UI; _execute skips completed ones.
        pass
    if mode == "step" and step in already and step != "normalization":
        # Allow re-running an incomplete-looking step; for fully complete stages
        # still allow explicit re-run (user confirmed) — do not block.
        pass

    global _active_job_id, _worker
    with _lock:
        if _active_job_id:
            active = _jobs.get(_active_job_id)
            if active and active.status in ("queued", "running"):
                raise RuntimeError(
                    f"Job {_active_job_id} is already {active.status}. Wait for it to finish."
                )
        job_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid4().hex[:8]
        log_path = RUNS_DIR / f"{job_id}.log"
        RUNS_DIR.mkdir(parents=True, exist_ok=True)
        resume_note = ""
        if already:
            nxt = next((s for s in steps if s not in already), None)
            resume_note = (
                f"Resume from {STEP_META[nxt]['name']}."
                if nxt
                else "All requested stages already complete."
            )
        job = PipelineJob(
            id=job_id,
            mode=mode,
            steps=steps,
            status="queued",
            created_at=_now(),
            updated_at=_now(),
            confirm=True,
            batch_id=batch_id,
            project_id=project_id,
            framework=fw,
            output_dir=str(output_root),
            log_path=str(log_path),
            message=resume_note or "Queued",
            step_pct=0,
            completed_steps=list(already) if mode == "full" else [],
        )
        _jobs[job_id] = job
        _active_job_id = job_id
        _persist(job)
        _worker = threading.Thread(target=_execute, args=(job,), daemon=True)
        _worker.start()
        return job
