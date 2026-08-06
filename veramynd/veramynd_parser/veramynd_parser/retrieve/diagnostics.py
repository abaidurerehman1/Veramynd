"""Per-lesson retrieval diagnostics (query → dense/BM25 → RRF → rerank)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..text_utils import atomic_write_text
from .models import Candidate


def _rank_map(codes: list[str]) -> dict[str, int]:
    return {c: i for i, c in enumerate(codes, start=1)}


def _best_arm_ranks(
    per_query: list[dict[str, Any]], field: str
) -> dict[str, int]:
    best: dict[str, int] = {}
    for query in per_query:
        for rank, code in enumerate(query.get(field) or [], start=1):
            prior = best.get(code)
            if prior is None or rank < prior:
                best[code] = rank
    return best


def candidate_stage_rows(
    *,
    per_query: list[dict[str, Any]],
    merged_codes: list[str],
    reranked_codes: list[str],
    final_codes: list[str],
) -> list[dict[str, Any]]:
    """One deterministic row per candidate with every retrieval-stage rank."""
    dense = _best_arm_ranks(per_query, "dense_codes")
    bm25 = _best_arm_ranks(per_query, "bm25_codes")
    rrf = _rank_map(merged_codes)
    rerank = _rank_map(reranked_codes)
    final = _rank_map(final_codes)
    ordered_codes = list(
        dict.fromkeys(
            [*final_codes, *reranked_codes, *merged_codes, *dense, *bm25]
        )
    )
    rows: list[dict[str, Any]] = []
    for code in ordered_codes:
        dense_rank = dense.get(code)
        bm25_rank = bm25.get(code)
        arm_ranks = [rank for rank in (dense_rank, bm25_rank) if rank is not None]
        best_arm_rank = min(arm_ranks) if arm_ranks else None
        rrf_rank = rrf.get(code)
        reranker_rank = rerank.get(code)
        final_rank = final.get(code)
        rows.append(
            {
                "standard_code": code,
                "dense_rank": dense_rank,
                "bm25_rank": bm25_rank,
                "rrf_rank": rrf_rank,
                "reranker_rank": reranker_rank,
                "final_rank": final_rank,
                "rank_deltas": {
                    "best_arm_to_rrf": (
                        rrf_rank - best_arm_rank
                        if rrf_rank is not None and best_arm_rank is not None
                        else None
                    ),
                    "rrf_to_reranker": (
                        reranker_rank - rrf_rank
                        if rrf_rank is not None and reranker_rank is not None
                        else None
                    ),
                    "reranker_to_final": (
                        final_rank - reranker_rank
                        if reranker_rank is not None and final_rank is not None
                        else None
                    ),
                },
            }
        )
    return rows


def gold_rank_movements(
    *,
    gold_codes: list[str],
    per_query: list[dict[str, Any]],
    merged_codes: list[str],
    reranked_codes: list[str],
    shortlist_codes: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Where each gold leaf appeared / was lost across funnel stages."""
    merged_rank = _rank_map(merged_codes)
    rerank_rank = _rank_map(reranked_codes)
    shortlist_rank = _rank_map(shortlist_codes or reranked_codes)
    dense_best = _best_arm_ranks(per_query, "dense_codes")
    bm25_best = _best_arm_ranks(per_query, "bm25_codes")
    out: list[dict[str, Any]] = []
    for code in gold_codes:
        q_hits = []
        for q in per_query:
            dens = _rank_map(q.get("dense_codes") or [])
            bm = _rank_map(q.get("bm25_codes") or [])
            hyb = _rank_map(q.get("hybrid_codes") or [])
            if code in dens or code in bm or code in hyb:
                q_hits.append(
                    {
                        "query_id": q.get("query_id"),
                        "source": q.get("source"),
                        "dense_rank": dens.get(code),
                        "bm25_rank": bm.get(code),
                        "hybrid_rank": hyb.get(code),
                    }
                )
        m = merged_rank.get(code)
        r = rerank_rank.get(code)
        s = shortlist_rank.get(code)
        lost_at = None
        if not q_hits:
            lost_at = "never_retrieved"
        elif m is None:
            lost_at = "merge_rrf"
        elif r is None:
            lost_at = "rerank"
        elif s is None:
            lost_at = "shortlist"
        out.append(
            {
                "standard_code": code,
                "query_hits": q_hits,
                "dense_rank": dense_best.get(code),
                "bm25_rank": bm25_best.get(code),
                "rrf_rank": m,
                "merge_rrf_rank": m,
                "reranker_rank": r,
                "rerank_rank": r,
                "final_rank": s,
                "shortlist_rank": s,
                "rank_deltas": {
                    "rrf_to_reranker": (
                        r - m if m is not None and r is not None else None
                    ),
                    "reranker_to_final": (
                        s - r if r is not None and s is not None else None
                    ),
                },
                "lost_at": lost_at,
            }
        )
    return out


def build_diagnostics_payload(
    *,
    resource_id: str,
    queries: list[dict[str, str]],
    per_query: list[dict[str, Any]],
    merged: list[Candidate],
    reranked: list[Candidate],
    shortlist: list[Candidate] | None = None,
    gold_codes: list[str] | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    merged_codes = [c.standard_code for c in merged]
    reranked_codes = [c.standard_code for c in reranked]
    shortlist_codes = [c.standard_code for c in (shortlist or reranked)]
    payload: dict[str, Any] = {
        "schema_version": "1.1-retrieve-diagnostics",
        "resource_id": resource_id,
        "n_queries": len(queries),
        "generated_queries": queries,
        "per_query": per_query,
        "merge_rrf": {
            "n": len(merged),
            "codes": merged_codes,
        },
        "reranked": {
            "n": len(reranked),
            "codes": reranked_codes,
        },
        "shortlist": {
            "n": len(shortlist_codes),
            "codes": shortlist_codes,
        },
        "candidate_stage_ranks": candidate_stage_rows(
            per_query=per_query,
            merged_codes=merged_codes,
            reranked_codes=reranked_codes,
            final_codes=shortlist_codes,
        ),
        "gold_rank_movements": gold_rank_movements(
            gold_codes=list(gold_codes or []),
            per_query=per_query,
            merged_codes=merged_codes,
            reranked_codes=reranked_codes,
            shortlist_codes=shortlist_codes,
        )
        if gold_codes
        else [],
    }
    if extra:
        payload["extra"] = extra
    return payload


def write_diagnostics(path: Path | str, payload: dict[str, Any]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(p, json.dumps(payload, indent=2) + "\n")


__all__ = [
    "build_diagnostics_payload",
    "candidate_stage_rows",
    "gold_rank_movements",
    "write_diagnostics",
]
