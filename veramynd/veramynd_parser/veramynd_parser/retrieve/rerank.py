"""Cross-encoder rerank for hybrid candidates (local bge-reranker by default)."""

from __future__ import annotations

import os
from typing import Any, Callable

from .models import Candidate

DEFAULT_RERANK_MODEL = "BAAI/bge-reranker-base"
DEFAULT_RERANK_TOP_N = 10

# Process-local CrossEncoder cache (model load is expensive).
_CROSS_ENCODER_CACHE: dict[str, Any] = {}


class RerankError(RuntimeError):
    pass


def resolve_rerank_model(explicit: str | None = None) -> str:
    if explicit and explicit.strip():
        return explicit.strip()
    return (os.environ.get("RERANK_MODEL") or DEFAULT_RERANK_MODEL).strip()


def _get_cross_encoder(model_id: str) -> Any:
    hit = _CROSS_ENCODER_CACHE.get(model_id)
    if hit is not None:
        return hit
    try:
        from sentence_transformers import CrossEncoder
    except ImportError as e:
        raise RerankError(
            "sentence-transformers required for cross-encoder rerank. "
            "Install with: pip install -e '.[retrieve]'"
        ) from e
    print(f"Loading cross-encoder {model_id} (once per process)...", flush=True)
    model = CrossEncoder(model_id)
    _CROSS_ENCODER_CACHE.clear()
    _CROSS_ENCODER_CACHE[model_id] = model
    return model


def cross_encoder_scores(
    query: str,
    documents: list[str],
    *,
    model_id: str = DEFAULT_RERANK_MODEL,
) -> list[float]:
    """Score (query, document) pairs with a local CrossEncoder."""
    if not documents:
        return []
    model = _get_cross_encoder(model_id)
    pairs = [(query, doc) for doc in documents]
    raw = model.predict(pairs, convert_to_numpy=True)
    return [float(x) for x in raw]


def rerank_candidates(
    query: str,
    candidates: list[Candidate],
    *,
    top_n: int = DEFAULT_RERANK_TOP_N,
    model_id: str | None = None,
    score_fn: Callable[[str, list[str]], list[float]] | None = None,
) -> list[Candidate]:
    """Rerank hybrid candidates with a cross-encoder; return top_n."""
    if top_n < 1:
        raise ValueError(f"top_n must be >= 1, got {top_n}")
    if not candidates:
        return []
    q = (query or "").strip()
    if not q:
        raise RerankError("empty query for rerank")

    docs = [c.text for c in candidates]
    mid = resolve_rerank_model(model_id)
    encode = score_fn or (
        lambda query_text, documents: cross_encoder_scores(
            query_text, documents, model_id=mid
        )
    )
    scores = encode(q, docs)
    if len(scores) != len(candidates):
        raise RerankError(
            f"rerank returned {len(scores)} scores for {len(candidates)} candidates"
        )

    ranked = sorted(
        zip(candidates, scores, strict=True),
        key=lambda pair: (-pair[1], pair[0].standard_code),
    )
    out: list[Candidate] = []
    for cand, score in ranked[:top_n]:
        out.append(
            Candidate(
                standard_code=cand.standard_code,
                text=cand.text,
                rrf_score=cand.rrf_score,
                dense_rank=cand.dense_rank,
                bm25_rank=cand.bm25_rank,
                dense_score=cand.dense_score,
                bm25_score=cand.bm25_score,
                rerank_score=float(score),
                domain_primary=cand.domain_primary,
                label=cand.label,
                level=cand.level,
                grade=cand.grade,
            )
        )
    return out


__all__ = [
    "DEFAULT_RERANK_MODEL",
    "DEFAULT_RERANK_TOP_N",
    "RerankError",
    "cross_encoder_scores",
    "rerank_candidates",
    "resolve_rerank_model",
]
