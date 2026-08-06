"""Reciprocal Rank Fusion for hybrid retrieval lists."""

from __future__ import annotations

import math
from typing import Any

MERGE_AGGREGATIONS = ("sum", "max", "top_k_sum", "log_dampened")
POOL_MEMBERSHIP_MODES = ("single", "union")


def reciprocal_rank_fusion(
    ranked_id_lists: list[list[str]],
    *,
    k: int = 60,
    weights: list[float] | None = None,
) -> list[tuple[str, float]]:
    """Fuse multiple ranked ID lists with classic summed RRF.

    ``score(d) = sum_i w_i / (k + rank_i(d))`` where rank is 1-based.
    Optional ``weights`` (default 1.0 per list) up-weights high-signal query
    arms (objective / skills / vocabulary) in multi-query merges.
    Returns ``(id, score)`` sorted by score descending. Stable for ties by id.
    """
    scored, _arms = aggregate_multi_arm_rrf(
        ranked_id_lists,
        k=k,
        weights=weights,
        aggregation="sum",
    )
    return scored


def aggregate_multi_arm_rrf(
    ranked_id_lists: list[list[str]],
    *,
    k: int = 60,
    weights: list[float] | None = None,
    sources: list[str] | None = None,
    aggregation: str = "sum",
    top_arms: int = 2,
    log_dampen_base: float = 2.0,
) -> tuple[list[tuple[str, float]], dict[str, list[dict[str, Any]]]]:
    """Fuse ranked ID lists with selectable multi-arm aggregation.

    Per-arm contribution is always ``w_i / (k + rank_i)``. Aggregation modes:

    - ``sum``: sum all arm contributions (classic RRF; rewards breadth)
    - ``max``: keep only the strongest single-arm contribution (rewards depth)
    - ``top_k_sum``: sum the best ``top_arms`` contributions only
    - ``log_dampened``: ``(sum contributions) * log_b(1+n_hits) / n_hits``

    Returns ``(sorted (id, score), arm_provenance_by_id)``. Provenance entries
    include query index, optional source label, rank, weight, and contribution.
    """
    if k < 1:
        raise ValueError(f"RRF k must be >= 1, got {k}")
    mode = (aggregation or "sum").strip().lower()
    if mode not in MERGE_AGGREGATIONS:
        raise ValueError(
            f"aggregation must be one of {MERGE_AGGREGATIONS}, got {aggregation!r}"
        )
    if top_arms < 1:
        raise ValueError(f"top_arms must be >= 1, got {top_arms}")
    if log_dampen_base <= 1.0:
        raise ValueError(f"log_dampen_base must be > 1, got {log_dampen_base}")

    if weights is None:
        weights = [1.0] * len(ranked_id_lists)
    if len(weights) != len(ranked_id_lists):
        raise ValueError(
            f"weights length {len(weights)} != ranked_id_lists {len(ranked_id_lists)}"
        )
    if sources is not None and len(sources) != len(ranked_id_lists):
        raise ValueError(
            f"sources length {len(sources)} != ranked_id_lists {len(ranked_id_lists)}"
        )

    contributions: dict[str, list[dict[str, Any]]] = {}
    for arm_index, (ranking, weight) in enumerate(
        zip(ranked_id_lists, weights, strict=True), start=1
    ):
        w = float(weight)
        if w < 0:
            raise ValueError(f"RRF weight must be >= 0, got {w}")
        if w == 0.0:
            continue
        source = ""
        if sources is not None:
            source = str(sources[arm_index - 1] or "")
        seen: set[str] = set()
        for rank, doc_id in enumerate(ranking, start=1):
            if not doc_id or doc_id in seen:
                continue
            seen.add(doc_id)
            contrib = w / (k + rank)
            contributions.setdefault(doc_id, []).append(
                {
                    "query_index": arm_index,
                    "source": source,
                    "rank": rank,
                    "weight": w,
                    "contribution": float(contrib),
                }
            )

    scores: dict[str, float] = {}
    for doc_id, arms in contributions.items():
        ordered = sorted(
            arms,
            key=lambda row: (-float(row["contribution"]), int(row["rank"]), int(row["query_index"])),
        )
        if mode == "sum":
            scores[doc_id] = sum(float(row["contribution"]) for row in ordered)
        elif mode == "max":
            scores[doc_id] = float(ordered[0]["contribution"]) if ordered else 0.0
        elif mode == "top_k_sum":
            scores[doc_id] = sum(
                float(row["contribution"]) for row in ordered[:top_arms]
            )
        else:  # log_dampened
            raw = sum(float(row["contribution"]) for row in ordered)
            n_hits = len(ordered)
            dampen = math.log(1.0 + n_hits, log_dampen_base) / float(n_hits)
            scores[doc_id] = raw * dampen

    ranked = sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))
    return ranked, contributions


def select_merge_pool(
    primary_ranked: list[tuple[str, float]],
    *,
    merge_top_k: int,
    pool_membership_mode: str = "single",
    secondary_sum_ranked: list[tuple[str, float]] | None = None,
) -> tuple[list[tuple[str, float]], dict[str, Any]]:
    """Build the merge pool with optional sum-side membership union.

    Ordering and scores always come from ``primary_ranked`` (the selected
    merge aggregation). ``union`` only expands membership:

    pool = top_k(primary) ∪ top_k(sum)

    Candidates that enter only via the sum side keep their primary
    aggregation score (even if outside primary top_k) so relative order
    among primary-qualified docs is unchanged; union docs sort after them
    by primary score.
    """
    if merge_top_k < 1:
        raise ValueError(f"merge_top_k must be >= 1, got {merge_top_k}")
    mode = (pool_membership_mode or "single").strip().lower()
    if mode not in POOL_MEMBERSHIP_MODES:
        raise ValueError(
            f"pool_membership_mode must be one of {POOL_MEMBERSHIP_MODES}, "
            f"got {pool_membership_mode!r}"
        )

    primary_top = primary_ranked[:merge_top_k]
    stats: dict[str, Any] = {
        "pool_membership_mode": mode,
        "primary_pool_n": len(primary_top),
        "sum_pool_n": 0,
        "union_added_n": 0,
        "final_pool_n": len(primary_top),
    }
    if mode == "single":
        return list(primary_top), stats

    if secondary_sum_ranked is None:
        raise ValueError("secondary_sum_ranked is required when pool_membership_mode='union'")

    primary_scores = {code: float(score) for code, score in primary_ranked}
    primary_ids = [code for code, _ in primary_top]
    primary_set = set(primary_ids)
    sum_ids = [code for code, _ in secondary_sum_ranked[:merge_top_k]]
    sum_set = set(sum_ids)
    added = [code for code in sum_ids if code not in primary_set]
    selected = primary_set | sum_set

    # Preserve relative order of primary-qualified docs exactly; append
    # union-only docs sorted by primary score (stable by id).
    ordered: list[tuple[str, float]] = list(primary_top)
    for code in sorted(
        added,
        key=lambda c: (-primary_scores.get(c, 0.0), c),
    ):
        ordered.append((code, float(primary_scores.get(code, 0.0))))

    # Defensive: if a sum-only code somehow lacks a primary score entry,
    # it still appears with 0.0 so CE can see it.
    stats["sum_pool_n"] = len(sum_ids)
    stats["union_added_n"] = len(added)
    stats["final_pool_n"] = len(ordered)
    stats["selected_n"] = len(selected)
    return ordered, stats


__all__ = [
    "MERGE_AGGREGATIONS",
    "POOL_MEMBERSHIP_MODES",
    "aggregate_multi_arm_rrf",
    "reciprocal_rank_fusion",
    "select_merge_pool",
]
