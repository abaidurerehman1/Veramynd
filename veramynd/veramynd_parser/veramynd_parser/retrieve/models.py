"""Retrieval candidates for lesson → standards hybrid search."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class StandardDoc:
    """One embeddable / searchable standard (leaf after filter)."""

    standard_code: str
    text: str
    domain_primary: str = ""
    parent_code: str = ""
    label: str = ""
    level: str = ""
    grade: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class Candidate:
    """A retrieved standard with funnel diagnostics."""

    standard_code: str
    text: str
    # Stage ranks are one-based. ``None`` means the candidate did not appear
    # in that stage (for example, an exhaustive local-CE addition).
    rrf_score: float = 0.0
    dense_rank: int | None = None
    bm25_rank: int | None = None
    rrf_rank: int | None = None
    dense_score: float | None = None
    bm25_score: float | None = None
    rerank_score: float | None = None
    blended_score: float | None = None
    rerank_rank: int | None = None
    final_rank: int | None = None
    # How many focused queries retrieved this leaf in the per-query hybrid top-k
    # (and the query-weight sum of those hits). Used to prefer multi-arm agreement
    # over one lucky dense/BM25 dual hit from a noisy query.
    query_hits: int = 0
    query_hit_weight: float = 0.0
    # Per focused-query hybrid rank provenance for merge auditing / offline
    # re-aggregation. Each entry: query_index, source, rank, weight, contribution.
    arm_hits: list[dict[str, Any]] = field(default_factory=list)
    # Classic sum-aggregation rank (1-based) when computed for shortlist rescue.
    sum_rank: int | None = None
    # Set when shortlist rescue admits a candidate via sum-rank slots.
    rescued_via: str | None = None
    domain_primary: str = ""
    parent_code: str = ""
    label: str = ""
    level: str = ""
    grade: int | None = None

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        # Omit unset rescue provenance so default shortlist JSON stays unchanged.
        if data.get("rescued_via") is None:
            data.pop("rescued_via", None)
        if data.get("sum_rank") is None:
            data.pop("sum_rank", None)
        return data


__all__ = ["Candidate", "StandardDoc"]
