"""Reciprocal Rank Fusion for hybrid retrieval lists."""

from __future__ import annotations


def reciprocal_rank_fusion(
    ranked_id_lists: list[list[str]],
    *,
    k: int = 60,
) -> list[tuple[str, float]]:
    """Fuse multiple ranked ID lists with RRF.

    ``score(d) = sum_i 1 / (k + rank_i(d))`` where rank is 1-based.
    Returns ``(id, score)`` sorted by score descending. Stable for ties by id.
    """
    if k < 1:
        raise ValueError(f"RRF k must be >= 1, got {k}")
    scores: dict[str, float] = {}
    for ranking in ranked_id_lists:
        seen: set[str] = set()
        for rank, doc_id in enumerate(ranking, start=1):
            if not doc_id or doc_id in seen:
                continue
            seen.add(doc_id)
            scores[doc_id] = scores.get(doc_id, 0.0) + 1.0 / (k + rank)
    return sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))


__all__ = ["reciprocal_rank_fusion"]
