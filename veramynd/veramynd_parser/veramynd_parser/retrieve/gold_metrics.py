"""Retrieve-side gold metrics (does not modify the evaluation pipeline)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def _load_gold_pairs(gold_jsonl: Path | str) -> list[dict[str, Any]]:
    path = Path(gold_jsonl)
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        row = json.loads(line)
        if not isinstance(row, dict):
            continue
        status = (row.get("matched_status") or "").strip().lower()
        if status not in {"full", "partial"}:
            continue
        code = (row.get("standard_code") or "").strip()
        rid = (row.get("resource_id") or "").strip()
        if code and rid:
            rows.append(row)
    return rows


def resource_ids_from_gold(gold_jsonl: Path | str) -> list[str]:
    """Unique lesson ids present in a gold JSONL (order-stable)."""
    seen: set[str] = set()
    out: list[str] = []
    path = Path(gold_jsonl)
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        row = json.loads(line)
        rid = (row.get("resource_id") or "").strip()
        if rid and rid not in seen:
            seen.add(rid)
            out.append(rid)
    return out


def _codes_from_retrieve(path: Path, *, field: str) -> list[str]:
    data = json.loads(path.read_text(encoding="utf-8"))
    rows = data.get(field) or data.get("candidates") or []
    return [
        (c.get("standard_code") or "").strip()
        for c in rows
        if isinstance(c, dict) and (c.get("standard_code") or "").strip()
    ]


def report_leaf_recall(
    gold_jsonl: Path | str,
    retrieve_dir: Path | str,
    *,
    cutoffs: tuple[int, ...] = (10, 15, 20, 30, 40, 50),
) -> dict[str, Any]:
    """Compute leaf recall@k + MRR from retrieve artifacts vs gold positives."""
    gold = _load_gold_pairs(gold_jsonl)
    root = Path(retrieve_dir)
    cutoffs = tuple(sorted(set(int(x) for x in cutoffs if int(x) > 0)))

    def _eval(field: str) -> dict[str, Any]:
        hits = {k: 0 for k in cutoffs}
        rr_sum = 0.0
        n = 0
        missing_files = 0
        for g in gold:
            n += 1
            path = root / f"{g['resource_id']}.json"
            if not path.is_file():
                missing_files += 1
                continue
            codes = _codes_from_retrieve(path, field=field)
            code = g["standard_code"]
            if code in codes:
                rank = codes.index(code) + 1
                rr_sum += 1.0 / rank
                for k in cutoffs:
                    if rank <= k:
                        hits[k] += 1
        return {
            "n_positives": n,
            "missing_retrieve_files": missing_files,
            "mrr": round(rr_sum / n, 4) if n else 0.0,
            "recall": {
                f"@{k}": {
                    "hits": hits[k],
                    "n": n,
                    "rate": round(hits[k] / n, 4) if n else 0.0,
                }
                for k in cutoffs
            },
        }

    # After-rerank list + pre-rerank funnel when present.
    after = _eval("candidates")
    before = _eval("rrf_candidates")

    # Candidate counts from first available gold lesson file.
    before_n = after_n = None
    for g in gold:
        path = root / f"{g['resource_id']}.json"
        if not path.is_file():
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        after_n = len(data.get("candidates") or [])
        before_n = len(data.get("rrf_candidates") or data.get("candidates") or [])
        break

    return {
        "gold_source": str(gold_jsonl),
        "retrieve_dir": str(retrieve_dir),
        "candidate_count_before_rerank": before_n,
        "candidate_count_after_rerank": after_n,
        "after_rerank": after,
        "before_rerank_rrf": before,
    }


__all__ = [
    "report_leaf_recall",
    "resource_ids_from_gold",
]
