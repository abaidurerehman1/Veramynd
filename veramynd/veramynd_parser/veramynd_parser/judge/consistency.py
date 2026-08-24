"""P3: cross-lesson consistency — same standard + same evidence type → same label."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from ..text_utils import atomic_write_text
from .grounding import normalize_for_grounding

_STATUS_ORDER = ("full", "partial", "none")
_MIN_TYPE_CHARS = 40
_TYPE_TOKEN_N = 12


def evidence_type_key(evidence: str) -> str | None:
    """Coarse fingerprint of evidence *type* (normalized leading content words).

    Empty / tiny quotes (typical ``none`` rows) return None — nothing to align.
    """
    norm = normalize_for_grounding(evidence or "")
    if len(norm) < _MIN_TYPE_CHARS:
        return None
    tokens = [t for t in norm.split() if len(t) > 1]
    if len(tokens) < 5:
        return None
    return " ".join(tokens[:_TYPE_TOKEN_N])


def _majority_status(statuses: list[str]) -> str | None:
    counts = Counter(s for s in statuses if s in _STATUS_ORDER)
    if not counts:
        return None
    top, n = counts.most_common(1)[0]
    if n > len(statuses) / 2:
        return top
    return None


def _merge_review_reason(existing: str, addition: str) -> str:
    parts = [p.strip() for p in (existing or "").split(";") if p.strip()]
    if addition and addition not in parts:
        parts.append(addition)
    return "; ".join(parts)


def apply_cross_lesson_consistency(
    rows: list[dict[str, Any]],
    *,
    reconcile: bool = True,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Flag (and optionally reconcile) inconsistent labels for the same evidence type.

    ``rows`` are mutable verdict dicts that must include at least
    ``resource_id``, ``standard_code``, ``matched_status``, ``evidence``.
    Returns (rows, summary).
    """
    groups: dict[tuple[str, str], list[int]] = defaultdict(list)
    for i, row in enumerate(rows):
        code = str(row.get("standard_code") or "").strip()
        key = evidence_type_key(str(row.get("evidence") or ""))
        if not code or not key:
            continue
        groups[(code, key)].append(i)

    conflicts = 0
    flagged = 0
    reconciled = 0
    conflict_examples: list[dict[str, Any]] = []

    for (code, key), idxs in groups.items():
        if len(idxs) < 2:
            continue
        statuses = [str(rows[i].get("matched_status") or "").strip().lower() for i in idxs]
        unique = {s for s in statuses if s}
        if len(unique) < 2:
            continue

        conflicts += 1
        peers = sorted(
            {
                str(rows[i].get("resource_id") or "")
                for i in idxs
                if rows[i].get("resource_id")
            }
        )
        status_map = {
            str(rows[i].get("resource_id") or f"row{i}"): statuses[j]
            for j, i in enumerate(idxs)
        }
        majority = _majority_status(statuses) if reconcile else None
        reason = (
            f"cross-lesson inconsistency: {code} labels={dict(Counter(statuses))} "
            f"peers={peers}"
        )
        if majority:
            reason = f"{reason}; reconciled→{majority}"

        if len(conflict_examples) < 8:
            conflict_examples.append(
                {
                    "standard_code": code,
                    "evidence_type_key": key,
                    "labels": status_map,
                    "majority": majority,
                }
            )

        for i in idxs:
            row = rows[i]
            row["needs_review"] = True
            row["review_reason"] = _merge_review_reason(
                str(row.get("review_reason") or ""), reason
            )
            if str(row.get("confidence") or "").lower() == "high":
                row["confidence"] = "low"
            flagged += 1

            if majority and str(row.get("matched_status") or "").lower() != majority:
                old = row.get("matched_status")
                row["matched_status"] = majority
                rationale = str(row.get("rationale") or "")
                note = (
                    f" [P3 CONSISTENCY: was {old}, aligned to {majority} "
                    f"to match same evidence type across {peers}]"
                )
                if note.strip() not in rationale:
                    row["rationale"] = (rationale + note).strip()
                reconciled += 1

    summary = {
        "groups_checked": len(groups),
        "conflict_groups": conflicts,
        "rows_flagged": flagged,
        "rows_reconciled": reconciled,
        "examples": conflict_examples,
    }
    return rows, summary


def apply_consistency_to_judge_dir(
    judge_dir: Path | str,
    *,
    reconcile: bool = True,
    rewrite: bool = True,
) -> dict[str, Any]:
    """Load all judge JSON reports, apply P3, optionally rewrite files."""
    root = Path(judge_dir)
    files = sorted(
        p
        for p in root.glob("*.json")
        if p.is_file() and not p.name.endswith(".incomplete.json")
    )
    # Flat index of (file_idx, verdict_idx) so we can write back.
    rows: list[dict[str, Any]] = []
    owners: list[tuple[int, int]] = []
    reports: list[dict[str, Any]] = []

    for fi, path in enumerate(files):
        data = json.loads(path.read_text(encoding="utf-8"))
        reports.append(data)
        verdicts = data.get("verdicts") or []
        if not isinstance(verdicts, list):
            continue
        for vi, v in enumerate(verdicts):
            if not isinstance(v, dict):
                continue
            row = dict(v)
            if not row.get("resource_id"):
                row["resource_id"] = data.get("resource_id") or path.stem
            rows.append(row)
            owners.append((fi, vi))

    _, summary = apply_cross_lesson_consistency(rows, reconcile=reconcile)

    if rewrite and summary.get("rows_flagged"):
        # Push mutated rows back into report objects.
        for row, (fi, vi) in zip(rows, owners):
            reports[fi]["verdicts"][vi] = row
        for path, report in zip(files, reports):
            atomic_write_text(path, json.dumps(report, indent=2, ensure_ascii=False) + "\n")

    summary["judge_files"] = len(files)
    summary["verdict_rows"] = len(rows)
    return summary


__all__ = [
    "apply_consistency_to_judge_dir",
    "apply_cross_lesson_consistency",
    "evidence_type_key",
]
