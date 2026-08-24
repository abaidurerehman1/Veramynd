"""P9: confirm dense_score=0 with healthy dense_rank is a logging artifact.

RRF fusion uses ranks, not raw dense scores. When ``dense_rank`` is populated
with distinct values but every ``dense_score`` is 0/null, retrieval still ran;
the score column is cosmetic and must not block shipping.
"""

from __future__ import annotations

from typing import Any, Iterable, Mapping


def _iter_rows(
    candidates: Iterable[Any],
) -> list[Mapping[str, Any]]:
    rows: list[Mapping[str, Any]] = []
    for c in candidates:
        if isinstance(c, Mapping):
            rows.append(c)
        else:
            rows.append(
                {
                    "dense_rank": getattr(c, "dense_rank", None),
                    "dense_score": getattr(c, "dense_score", None),
                    "bm25_rank": getattr(c, "bm25_rank", None),
                }
            )
    return rows


def assess_dense_score_health(candidates: Iterable[Any]) -> dict[str, Any]:
    """Classify dense_score logging vs real dense-arm failure.

    Returns a JSON-friendly dict with:
      - status: ok | logging_artifact | dense_arm_missing | empty
      - retrieval_ok: whether RRF dense ranks look usable
      - note: short engineer-facing explanation
    """
    rows = _iter_rows(candidates)
    if not rows:
        return {
            "status": "empty",
            "retrieval_ok": False,
            "dense_rank_n": 0,
            "distinct_dense_ranks": 0,
            "positive_dense_score_n": 0,
            "note": "no candidates to assess",
        }

    ranks: list[int] = []
    positive_scores = 0
    zeroish_scores = 0
    scored = 0
    for row in rows:
        r = row.get("dense_rank")
        if r is not None:
            try:
                ranks.append(int(r))
            except (TypeError, ValueError):
                pass
        s = row.get("dense_score")
        if s is None:
            continue
        scored += 1
        try:
            val = float(s)
        except (TypeError, ValueError):
            continue
        if val > 0.0:
            positive_scores += 1
        else:
            zeroish_scores += 1

    distinct = len(set(ranks))
    if positive_scores > 0:
        return {
            "status": "ok",
            "retrieval_ok": True,
            "dense_rank_n": len(ranks),
            "distinct_dense_ranks": distinct,
            "positive_dense_score_n": positive_scores,
            "note": "dense_score populated; dense arm logging looks healthy",
        }

    if len(ranks) >= 2 and distinct >= 2:
        return {
            "status": "logging_artifact",
            "retrieval_ok": True,
            "dense_rank_n": len(ranks),
            "distinct_dense_ranks": distinct,
            "positive_dense_score_n": 0,
            "zero_or_null_score_n": zeroish_scores + (len(rows) - scored),
            "note": (
                "dense_rank is populated with distinct ranks so the dense "
                "retriever ran; RRF fuses by rank. dense_score=0 is cosmetic "
                "logging — do not treat as recall failure."
            ),
        }

    if not ranks:
        return {
            "status": "dense_arm_missing",
            "retrieval_ok": False,
            "dense_rank_n": 0,
            "distinct_dense_ranks": 0,
            "positive_dense_score_n": 0,
            "note": (
                "no dense_rank values — dense arm missing or unused; "
                "investigate embeddings / Qdrant, and route empty retrieval "
                "to needs_review rather than silent none."
            ),
        }

    return {
        "status": "unknown",
        "retrieval_ok": bool(ranks),
        "dense_rank_n": len(ranks),
        "distinct_dense_ranks": distinct,
        "positive_dense_score_n": positive_scores,
        "note": "insufficient signal to classify dense_score health",
    }


def scan_retrieve_dir_dense_health(retrieve_dir: str | Any) -> dict[str, Any]:
    """Scan ``*.json`` retrieve files and summarize P9 dense_score health."""
    from pathlib import Path
    import json

    root = Path(retrieve_dir)
    by_status: dict[str, list[str]] = {}
    files = 0
    for path in sorted(root.glob("*.json")):
        if path.name.endswith(".incomplete.json"):
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        cands = data.get("candidates") or data.get("rrf_candidates") or []
        if not isinstance(cands, list):
            continue
        files += 1
        health = assess_dense_score_health(cands)
        by_status.setdefault(str(health["status"]), []).append(path.stem)

    return {
        "retrieve_dir": str(root),
        "files_scanned": files,
        "by_status": {k: {"count": len(v), "ids": v} for k, v in by_status.items()},
        "confirmed_logging_artifact": (by_status.get("logging_artifact") or []) != [],
        "note": (
            "P9: logging_artifact means dense_score=0 with healthy dense_rank — "
            "safe to ignore for ranking; fix score serialization on next retrieve."
        ),
    }


__all__ = [
    "assess_dense_score_health",
    "scan_retrieve_dir_dense_health",
]
