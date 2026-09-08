"""Project registry — one Overview = one PDF + one XLSX + one output tree."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

DASHBOARD_ROOT = Path(__file__).resolve().parents[1]
VERAMYND_ROOT = DASHBOARD_ROOT.parent
REGISTRY_PATH = DASHBOARD_ROOT / "projects.json"


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

    def inputs_exist(self) -> tuple[bool, bool]:
        return self.guide_pdf.is_file(), self.standards_xlsx.is_file()


def _resolve_under(root: Path, rel: str) -> Path:
    p = Path(rel)
    if p.is_absolute():
        return p
    return (root / p).resolve()


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
    )


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
    return str(data.get("default_project_id") or data["projects"][0]["id"])


def list_project_configs() -> list[ProjectConfig]:
    return [_parse_project(p) for p in _registry().get("projects") or []]


def get_project_config(project_id: str | None = None) -> ProjectConfig:
    pid = (project_id or "").strip() or default_project_id()
    for cfg in list_project_configs():
        if cfg.id == pid:
            return cfg
    known = ", ".join(c.id for c in list_project_configs()) or "(none)"
    raise KeyError(f"Unknown project_id={pid!r}. Known: {known}")


def project_card(cfg: ProjectConfig) -> dict[str, Any]:
    """Lightweight list/detail payload for the UI project picker."""
    guide_ok, std_ok = cfg.inputs_exist()
    output_ok = (cfg.output_dir / "stage1").is_dir() or (cfg.output_dir / "judge").is_dir()
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
        "is_default": cfg.id == default_project_id(),
    }
