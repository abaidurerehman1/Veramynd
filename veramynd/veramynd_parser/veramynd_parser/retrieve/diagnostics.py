"""Per-lesson retrieval diagnostics (query → dense/BM25 → RRF → rerank)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..text_utils import atomic_write_text
from .models import Candidate


def _rank_map(codes: list[str]) -> dict[str, int]:
    return {c: i for i, c in enumerate(codes, start=1)}


def gold_rank_movements(
    *,
    gold_codes: list[str],
    per_query: list[dict[str, Any]],
    merged_codes: list[str],
    reranked_codes: list[str],
) -> list[dict[str, Any]]:
    """Where each gold leaf appeared / was lost across funnel stages."""
    merged_rank = _rank_map(merged_codes)
    rerank_rank = _rank_map(reranked_codes)
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
        lost_at = None
        if not q_hits:
            lost_at = "never_retrieved"
        elif m is None:
            lost_at = "merge_rrf"
        elif r is None:
            lost_at = "rerank"
        out.append(
            {
                "standard_code": code,
                "query_hits": q_hits,
                "merge_rrf_rank": m,
                "rerank_rank": r,
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
    gold_codes: list[str] | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    merged_codes = [c.standard_code for c in merged]
    reranked_codes = [c.standard_code for c in reranked]
    payload: dict[str, Any] = {
        "schema_version": "1.0-retrieve-diagnostics",
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
        "gold_rank_movements": gold_rank_movements(
            gold_codes=list(gold_codes or []),
            per_query=per_query,
            merged_codes=merged_codes,
            reranked_codes=reranked_codes,
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
    "gold_rank_movements",
    "write_diagnostics",
]
