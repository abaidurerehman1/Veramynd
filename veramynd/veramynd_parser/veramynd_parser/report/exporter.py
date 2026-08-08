"""Export alignment judge verdicts to CSV / summary JSON (client report)."""

from __future__ import annotations

import csv
import json
import os
from pathlib import Path
from typing import Any, Iterable

from ..text_utils import atomic_write_text

REPORT_SCHEMA_VERSION = "1.0-report"

# Client-facing columns — do not silently drop rows for missing confidence.
CSV_COLUMNS = [
    "resource_id",
    "standard_code",
    "matched_status",
    "confidence",
    "grounded",
    "evidence",
    "evidence_page",
    "rationale",
    "standard_raw_text",
    "judge_model",
    "prompt_version",
    "escalated",
    "rerank_score",
    "rrf_score",
    "dense_score",
    "bm25_score",
    "dense_rank",
    "bm25_rank",
    "grounding_note",
]


class ReportError(ValueError):
    pass


def load_judge_report(path: Path | str) -> dict[str, Any]:
    p = Path(path)
    if not p.is_file():
        raise ReportError(f"judge report not found: {p}")
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise ReportError(f"{p}: invalid JSON ({e})") from e
    if not isinstance(data, dict):
        raise ReportError(f"{p}: expected JSON object")
    if not isinstance(data.get("verdicts"), list):
        raise ReportError(f"{p}: missing verdicts[]")
    return data


def _looks_like_judge_report(p: Path) -> bool:
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return isinstance(data, dict) and isinstance(data.get("verdicts"), list)


def collect_judge_files(paths: Iterable[Path | str]) -> list[Path]:
    files: list[Path] = []
    for raw in paths:
        p = Path(raw)
        if p.is_dir():
            for f in sorted(p.glob("*.json")):
                # Dir globs must tolerate neighbors: incomplete-run sidecars
                # and non-judge JSON — including this exporter's own
                # alignments.summary.json when --out points into the judge dir,
                # which used to hard-fail every run after the first.
                if f.name.endswith(".incomplete.json"):
                    continue
                if not _looks_like_judge_report(f):
                    print(f"skipping non-judge JSON: {f}", flush=True)
                    continue
                files.append(f)
        elif p.is_file():
            # Explicitly named files always pass through — a user asking for a
            # specific .incomplete.json gets it (or a loud error), not silence.
            files.append(p)
        else:
            raise ReportError(f"path not found: {p}")
    if not files:
        raise ReportError("no judge JSON files found")
    return files


def verdict_to_row(v: dict[str, Any], *, resource_id: str | None = None) -> dict[str, Any]:
    retrieval = v.get("retrieval") or {}
    rid = (v.get("resource_id") or resource_id or "").strip()
    return {
        "resource_id": rid,
        "standard_code": (v.get("standard_code") or "").strip(),
        "matched_status": (v.get("matched_status") or "").strip(),
        "confidence": (v.get("confidence") or "").strip(),
        "grounded": v.get("grounded"),
        "evidence": v.get("evidence") or "",
        "evidence_page": v.get("evidence_page"),
        "rationale": v.get("rationale") or "",
        "standard_raw_text": v.get("standard_raw_text") or "",
        "judge_model": v.get("judge_model") or "",
        "prompt_version": v.get("prompt_version") or "",
        "escalated": v.get("escalated"),
        "rerank_score": retrieval.get("rerank_score"),
        "rrf_score": retrieval.get("rrf_score"),
        "dense_score": retrieval.get("dense_score"),
        "bm25_score": retrieval.get("bm25_score"),
        "dense_rank": retrieval.get("dense_rank"),
        "bm25_rank": retrieval.get("bm25_rank"),
        "grounding_note": v.get("grounding_note") or "",
    }


def build_rows(
    judge_files: list[Path],
    *,
    statuses: set[str] | None = None,
    grounded_only: bool = False,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Flatten judge verdicts into CSV rows.

    ``statuses`` filters matched_status when set (e.g. {full, partial}).
    Never drops rows for missing confidence.
    """
    rows: list[dict[str, Any]] = []
    by_status: dict[str, int] = {"full": 0, "partial": 0, "none": 0}
    sources: list[str] = []
    skipped_status = 0
    skipped_ungrounded = 0
    skipped_bad = 0

    for path in judge_files:
        data = load_judge_report(path)
        sources.append(str(path))
        rid = (data.get("resource_id") or path.stem).strip()
        for v in data.get("verdicts") or []:
            if not isinstance(v, dict):
                skipped_bad += 1
                continue
            row = verdict_to_row(v, resource_id=rid)
            status = row["matched_status"]
            if status in by_status:
                by_status[status] += 1
            else:
                by_status[status] = by_status.get(status, 0) + 1
            if statuses is not None and status not in statuses:
                skipped_status += 1
                continue
            if grounded_only and status != "none" and not row.get("grounded"):
                skipped_ungrounded += 1
                continue
            rows.append(row)

    if skipped_bad:
        raise ReportError(
            f"refusing report: {skipped_bad} non-object verdict(s) in judge JSON "
            "(corrupt input)"
        )

    summary = {
        "schema_version": REPORT_SCHEMA_VERSION,
        "source_files": sources,
        "row_count": len(rows),
        "by_status_all_verdicts": by_status,
        "filtered_out_by_status": skipped_status,
        "filtered_out_ungrounded": skipped_ungrounded,
        "status_filter": sorted(statuses) if statuses else None,
        "grounded_only": grounded_only,
    }
    return rows, summary


def write_csv(rows: list[dict[str, Any]], out: Path | str) -> Path:
    """Write the CSV via temp-file-then-replace, so a crash or concurrent reader
    can never observe a truncated/partial report (same pattern as
    ``text_utils.atomic_write_text``, adapted for a binary/DictWriter target)."""
    path = Path(out)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(f"{path.suffix}.{os.getpid()}.tmp")

    def _guard(row: dict[str, Any]) -> dict[str, Any]:
        # Formula-injection guard for the client-facing CSV: PDF/LLM-derived
        # text starting with =, +, -, or @ would execute as a formula when
        # opened in Excel/Sheets. Prefix with a quote (standard mitigation);
        # numeric/score columns are untouched.
        guarded = dict(row)
        for col in ("evidence", "rationale", "standard_raw_text", "grounding_note"):
            v = guarded.get(col)
            if isinstance(v, str) and v[:1] in ("=", "+", "-", "@"):
                guarded[col] = "'" + v
        return guarded

    try:
        with tmp.open("w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS, extrasaction="ignore")
            writer.writeheader()
            for row in rows:
                writer.writerow(_guard(row))
        tmp.replace(path)
        tmp = None  # type: ignore[assignment]
    finally:
        if tmp is not None and tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass
    return path


def write_summary(summary: dict[str, Any], out: Path | str) -> Path:
    path = Path(out)
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(path, json.dumps(summary, indent=2, ensure_ascii=False) + "\n")
    return path


def export_alignment_report(
    judge_paths: list[Path | str],
    *,
    out_csv: Path | str,
    out_summary: Path | str | None = None,
    include_none: bool = True,
    grounded_only: bool = False,
) -> dict[str, Any]:
    files = collect_judge_files(judge_paths)
    statuses: set[str] | None = None
    if not include_none:
        statuses = {"full", "partial"}
    rows, summary = build_rows(
        files, statuses=statuses, grounded_only=grounded_only
    )
    csv_path = write_csv(rows, out_csv)
    summary["csv_path"] = str(csv_path)
    if out_summary is None:
        out_summary = Path(out_csv).with_suffix(".summary.json")
    summary_path = write_summary(summary, out_summary)
    summary["summary_path"] = str(summary_path)
    return summary


__all__ = [
    "CSV_COLUMNS",
    "REPORT_SCHEMA_VERSION",
    "ReportError",
    "build_rows",
    "export_alignment_report",
    "load_judge_report",
    "write_csv",
]
