"""Project registry — one Overview = one PDF + one XLSX + one output tree.

Also exposes upload batches under ``backend/uploads/<id>/`` as virtual
projects (``upload-<id>``) so Overview / Pipeline work the same way without
hand-editing ``projects.json``.
"""

from __future__ import annotations

import json
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .layout import (
    BACKEND_ROOT,
    REGISTRY_PATH,
    UPLOADS_DIR,
    VERAMYND_ROOT,
)

# Back-compat for importers that still expect these names.
DASHBOARD_ROOT = BACKEND_ROOT
UPLOAD_PROJECT_PREFIX = "upload-"

_BATCH_ID_RE = re.compile(r"^[0-9A-Za-z][0-9A-Za-z._-]{0,79}$")


@dataclass(frozen=True)
class ProjectConfig:
    id: str
    name: str
    publisher: str
    grade: int | None
    subject: str
    module: str
    framework: str
    batch_label: str
    expected_lessons: int | None
    guide_pdf: Path
    standards_xlsx: Path
    output_dir: Path
    client_summary: Path
    client_docx: Path
    client_xlsx: Path
    gold_metrics: Path
    gold_jsonl: Path
    corrected_master: Path | None
    curriculum_pdf_label: str
    run_id: str
    # Relative display paths (repo-rooted under veramynd/)
    guide_pdf_rel: str = ""
    standards_xlsx_rel: str = ""
    output_dir_rel: str = ""
    source: str = "registry"  # registry | upload
    upload_batch_id: str = ""

    def inputs_exist(self) -> tuple[bool, bool]:
        return self.guide_pdf.is_file(), self.standards_xlsx.is_file()


def upload_project_id(batch_id: str) -> str:
    return f"{UPLOAD_PROJECT_PREFIX}{batch_id}"


def batch_id_from_project(project_id: str) -> str | None:
    if not project_id.startswith(UPLOAD_PROJECT_PREFIX):
        return None
    return project_id[len(UPLOAD_PROJECT_PREFIX) :]


def _resolve_under(root: Path, rel: str) -> Path:
    p = Path(rel)
    if p.is_absolute():
        return p
    return (root / p).resolve()


def _rel_to_veramynd(path: Path) -> str:
    try:
        return path.resolve().relative_to(VERAMYND_ROOT.resolve()).as_posix()
    except ValueError:
        return str(path)


def _load_raw() -> dict[str, Any]:
    if not REGISTRY_PATH.is_file():
        raise FileNotFoundError(f"Project registry missing: {REGISTRY_PATH}")
    return json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))


def _parse_project(raw: dict[str, Any]) -> ProjectConfig:
    inputs = dict(raw.get("inputs") or {})
    artifacts = dict(raw.get("artifacts") or {})
    labels = dict(raw.get("labels") or {})

    output_rel = str(raw.get("output_dir") or "veramynd_parser/output")
    output_dir = _resolve_under(VERAMYND_ROOT, output_rel)

    guide_rel = str(inputs.get("guide_pdf") or "")
    standards_rel = str(inputs.get("standards_xlsx") or "")

    master_rel = artifacts.get("corrected_master")
    corrected = (
        _resolve_under(VERAMYND_ROOT, str(master_rel)) if master_rel else None
    )

    def out_art(key: str, default: str) -> Path:
        return output_dir / str(artifacts.get(key) or default)

    return ProjectConfig(
        id=str(raw["id"]),
        name=str(raw.get("name") or raw["id"]),
        publisher=str(raw.get("publisher") or ""),
        grade=raw.get("grade"),
        subject=str(raw.get("subject") or ""),
        module=str(raw.get("module") or ""),
        framework=str(raw.get("framework") or ""),
        batch_label=str(raw.get("batch_label") or ""),
        expected_lessons=raw.get("expected_lessons"),
        guide_pdf=_resolve_under(VERAMYND_ROOT, guide_rel) if guide_rel else Path(),
        standards_xlsx=_resolve_under(VERAMYND_ROOT, standards_rel)
        if standards_rel
        else Path(),
        output_dir=output_dir,
        client_summary=out_art(
            "client_summary", "reports/client_correlation.summary.json"
        ),
        client_docx=out_art("client_docx", "reports/client_correlation.docx"),
        client_xlsx=out_art("client_xlsx", "reports/client_correlation.xlsx"),
        gold_metrics=out_art("gold_metrics", "reports/retrieve_gold_metrics.json"),
        gold_jsonl=out_art("gold_jsonl", "reports/gold_set.jsonl"),
        corrected_master=corrected,
        curriculum_pdf_label=str(
            labels.get("curriculum_pdf") or Path(guide_rel).name or raw.get("name") or ""
        ),
        run_id=str(labels.get("run_id") or f"{raw['id']}-run"),
        guide_pdf_rel=guide_rel,
        standards_xlsx_rel=standards_rel,
        output_dir_rel=output_rel,
        source="registry",
        upload_batch_id="",
    )


def _find_file(batch_dir: Path, exts: tuple[str, ...]) -> Path | None:
    for p in sorted(batch_dir.iterdir()):
        if p.is_file() and p.suffix.lower() in exts:
            return p
    return None


def _parse_grade(label: str) -> int | None:
    m = re.search(r"(\d+)", label or "")
    return int(m.group(1)) if m else None


def list_upload_project_configs() -> list[ProjectConfig]:
    """Virtual projects backed by ``backend/uploads/<batch_id>/``."""
    if not UPLOADS_DIR.is_dir():
        return []
    rows: list[ProjectConfig] = []
    for batch_dir in sorted(UPLOADS_DIR.iterdir(), reverse=True):
        if not batch_dir.is_dir():
            continue
        batch_id = batch_dir.name
        if not _BATCH_ID_RE.match(batch_id):
            continue
        meta: dict[str, Any] = {}
        meta_path = batch_dir / "meta.json"
        if meta_path.is_file():
            try:
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                meta = {}

        pdf = _find_file(batch_dir, (".pdf",))
        xlsx = _find_file(batch_dir, (".xlsx", ".xlsm"))
        # Need at least one input file to surface as a project
        if not pdf and not xlsx:
            continue

        program = str(meta.get("program_name") or "").strip()
        guide_label = str(meta.get("guide_label") or "").strip()
        grade_label = str(meta.get("grade_label") or "").strip()
        name = str(meta.get("display_name") or "").strip()
        if not name:
            name_bits = [b for b in [program, guide_label, grade_label] if b]
            name = " · ".join(name_bits) if name_bits else f"Upload {batch_id}"

        output_dir = batch_dir / "output"
        output_dir.mkdir(parents=True, exist_ok=True)
        guide_rel = _rel_to_veramynd(pdf) if pdf else ""
        std_rel = _rel_to_veramynd(xlsx) if xlsx else ""
        out_rel = _rel_to_veramynd(output_dir)

        pid = upload_project_id(batch_id)
        rows.append(
            ProjectConfig(
                id=pid,
                name=name,
                publisher=program,
                grade=_parse_grade(grade_label),
                subject=str(meta.get("subject") or ""),
                module=guide_label,
                framework=str(meta.get("framework") or ""),
                batch_label=batch_id,
                expected_lessons=None,
                guide_pdf=pdf if pdf else Path(),
                standards_xlsx=xlsx if xlsx else Path(),
                output_dir=output_dir,
                client_summary=output_dir / "reports" / "client_correlation.summary.json",
                client_docx=output_dir / "reports" / "client_correlation.docx",
                client_xlsx=output_dir / "reports" / "client_correlation.xlsx",
                gold_metrics=output_dir / "reports" / "retrieve_gold_metrics.json",
                gold_jsonl=output_dir / "reports" / "gold_set.jsonl",
                corrected_master=None,
                curriculum_pdf_label=pdf.name if pdf else name,
                run_id=f"upload-{batch_id}",
                guide_pdf_rel=guide_rel,
                standards_xlsx_rel=std_rel,
                output_dir_rel=out_rel,
                source="upload",
                upload_batch_id=batch_id,
            )
        )
        if len(rows) >= 40:
            break
    return rows


_registry_cache: dict[str, Any] | None = None


def reload_registry() -> None:
    global _registry_cache
    _registry_cache = None


def _registry() -> dict[str, Any]:
    global _registry_cache
    if _registry_cache is None:
        _registry_cache = _load_raw()
    return _registry_cache


def default_project_id() -> str:
    data = _registry()
    projects = data.get("projects") or []
    if not projects:
        return ""
    did = str(data.get("default_project_id") or "").strip()
    if did and any(str(p.get("id")) == did for p in projects):
        return did
    return str(projects[0]["id"])


def _has_pipeline_output(cfg: ProjectConfig) -> bool:
    return (cfg.output_dir / "stage1").is_dir() or (cfg.output_dir / "judge").is_dir()


def _project_run_status(cfg: ProjectConfig) -> str:
    judge = cfg.output_dir / "judge"
    if judge.is_dir() and any(judge.glob("*.json")):
        return "ready"
    if _has_pipeline_output(cfg):
        return "running"
    return "empty"


def list_project_configs(*, include_idle_uploads: bool = False) -> list[ProjectConfig]:
    """Registered projects + upload batches that already have pipeline output.

    Idle uploads (saved inputs only) stay on Ingestion — they are not listed as
    separate switcher projects next to completed registry work. Pass
    ``include_idle_uploads=True`` when resolving a specific upload id.
    """
    regs = [_parse_project(p) for p in _registry().get("projects") or []]
    reg_ids = {c.id for c in regs}
    uploads: list[ProjectConfig] = []
    for u in list_upload_project_configs():
        if u.id in reg_ids:
            continue
        if include_idle_uploads or _has_pipeline_output(u):
            uploads.append(u)
    return regs + uploads


def get_project_config(project_id: str | None = None) -> ProjectConfig:
    pid = (project_id or "").strip() or default_project_id()
    if not pid:
        raise KeyError("No projects available")
    for cfg in list_project_configs(include_idle_uploads=True):
        if cfg.id == pid:
            return cfg
    known = ", ".join(c.id for c in list_project_configs(include_idle_uploads=True)) or "(none)"
    raise KeyError(f"Unknown project_id={pid!r}. Known: {known}")


def _save_registry(data: dict[str, Any]) -> None:
    REGISTRY_PATH.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    reload_registry()


def delete_project(project_id: str) -> dict[str, Any]:
    """Delete a project.

    Upload projects: remove the entire ``uploads/<batch>/`` tree (inputs + output).
    Registry projects: remove the entry from ``projects.json`` only (disk artifacts
    under locked Batch-1 output are never deleted).
    """
    pid = (project_id or "").strip()
    if not pid:
        raise ValueError("project_id required")
    cfg = get_project_config(pid)

    if cfg.source == "upload":
        batch = cfg.upload_batch_id or batch_id_from_project(pid)
        if not batch:
            raise ValueError("Upload project missing batch id")
        batch_dir = (UPLOADS_DIR / batch).resolve()
        root = UPLOADS_DIR.resolve()
        try:
            batch_dir.relative_to(root)
        except ValueError as e:
            raise ValueError("Invalid upload path") from e
        if batch_dir == root or not batch_dir.is_dir():
            raise KeyError(f"Unknown upload batch: {batch}")
        shutil.rmtree(batch_dir)
        return {
            "ok": True,
            "project_id": pid,
            "source": "upload",
            "purged_artifacts": True,
            "batch_id": batch,
            "message": f"Deleted upload project {cfg.name} and its files.",
        }

    # Registry: unregister only
    data = _load_raw()
    before = list(data.get("projects") or [])
    after = [p for p in before if str(p.get("id")) != pid]
    if len(after) == len(before):
        raise KeyError(f"Unknown registry project: {pid}")
    data["projects"] = after
    if str(data.get("default_project_id") or "") == pid:
        data["default_project_id"] = str(after[0]["id"]) if after else ""
    _save_registry(data)
    return {
        "ok": True,
        "project_id": pid,
        "source": "registry",
        "purged_artifacts": False,
        "batch_id": None,
        "message": (
            f"Removed “{cfg.name}” from the project list. "
            "On-disk output folder was kept (registry projects do not wipe artifacts)."
        ),
    }


def project_card(cfg: ProjectConfig) -> dict[str, Any]:
    """Lightweight list/detail payload for the UI project picker."""
    guide_ok, std_ok = cfg.inputs_exist()
    output_ok = _has_pipeline_output(cfg)
    status = _project_run_status(cfg)
    return {
        "id": cfg.id,
        "name": cfg.name,
        "publisher": cfg.publisher,
        "grade": cfg.grade,
        "subject": cfg.subject,
        "module": cfg.module,
        "framework": cfg.framework,
        "batch_label": cfg.batch_label,
        "expected_lessons": cfg.expected_lessons,
        "output_dir": cfg.output_dir_rel,
        "inputs": {
            "guide_pdf": cfg.guide_pdf_rel,
            "standards_xlsx": cfg.standards_xlsx_rel,
            "guide_pdf_exists": guide_ok,
            "standards_xlsx_exists": std_ok,
        },
        "has_output": output_ok,
        "run_status": status,
        "is_default": bool(default_project_id()) and cfg.id == default_project_id(),
        "source": cfg.source,
        "upload_batch_id": cfg.upload_batch_id or None,
        "can_purge": cfg.source == "upload",
    }
