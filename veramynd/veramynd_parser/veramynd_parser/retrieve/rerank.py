"""Cross-encoder rerank for hybrid candidates (local bge-reranker by default)."""

from __future__ import annotations

import os
from typing import Any, Callable

from .models import Candidate

DEFAULT_RERANK_MODEL = "BAAI/bge-reranker-base"
DEFAULT_RERANK_TOP_N = 10
DEFAULT_RERANK_QUERY_CHARS = 2400
DEFAULT_RERANK_DOCUMENT_CHARS = 2400

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


def format_rerank_query(query: str) -> str:
    """Preserve section labels while bounding the unchanged CE query side."""
    text = "\n".join(
        cleaned
        for line in (query or "").splitlines()
        if (cleaned := " ".join(line.split()).strip())
    )
    return text[:DEFAULT_RERANK_QUERY_CHARS]


def format_rerank_document(document: str) -> str:
    """Keep official/structured standard context legible to the unchanged CE."""
    text = (document or "").strip()
    return text[:DEFAULT_RERANK_DOCUMENT_CHARS]


def _robust_minmax(values: list[float]) -> list[float]:
    """Deterministic clipped normalization that limits one outlier's influence."""
    if not values:
        return []
    # A single NaN logit would poison lo/hi/span and collapse EVERY normalized
    # score to 1.0 (min(1.0, nan) == 1.0 in CPython). Substitute the finite
    # minimum — a NaN score ranks that candidate last without touching others.
    finite = [float(v) for v in values if float(v) == float(v)]
    if not finite:
        return [0.5] * len(values)
    floor = min(finite)
    values = [float(v) if float(v) == float(v) else floor for v in values]
    ordered = sorted(values)
    if ordered[0] == ordered[-1]:
        return [0.5] * len(values)

    def percentile(p: float) -> float:
        pos = (len(ordered) - 1) * p
        lower = int(pos)
        upper = min(lower + 1, len(ordered) - 1)
        weight = pos - lower
        return ordered[lower] * (1.0 - weight) + ordered[upper] * weight

    lo = percentile(0.05) if len(ordered) >= 10 else ordered[0]
    hi = percentile(0.95) if len(ordered) >= 10 else ordered[-1]
    if hi <= lo:
        lo, hi = ordered[0], ordered[-1]
    span = (hi - lo) or 1.0
    return [max(0.0, min(1.0, (float(v) - lo) / span)) for v in values]


def rerank_candidates(
    query: str,
    candidates: list[Candidate],
    *,
    top_n: int = DEFAULT_RERANK_TOP_N,
    model_id: str | None = None,
    score_fn: Callable[[str, list[str]], list[float]] | None = None,
    blend_rrf: float = 0.0,
    preserve_rrf_top: int = 0,
) -> list[Candidate]:
    """Rerank hybrid candidates with a cross-encoder; return top_n.

    ``blend_rrf`` in [0,1] mixes normalized RRF rank-score with cross-encoder
    scores so strong first-stage hits are less likely to be dropped.

    ``preserve_rrf_top`` forces the first N RRF-ordered candidates into the
    output (then fills remaining slots by blended/rerank score).
    """
    if top_n < 1:
        raise ValueError(f"top_n must be >= 1, got {top_n}")
    if not candidates:
        return []
    if not 0.0 <= float(blend_rrf) <= 1.0:
        raise ValueError(f"blend_rrf must be in [0,1], got {blend_rrf}")
    if preserve_rrf_top < 0:
        raise ValueError(f"preserve_rrf_top must be >= 0, got {preserve_rrf_top}")

    q = (query or "").strip()
    if not q:
        raise RerankError("empty query for rerank")

    formatted_query = format_rerank_query(q)
    docs = [format_rerank_document(c.text) for c in candidates]
    mid = resolve_rerank_model(model_id)
    encode = score_fn or (
        lambda query_text, documents: cross_encoder_scores(
            query_text, documents, model_id=mid
        )
    )
    scores = encode(formatted_query, docs)
    if len(scores) != len(candidates):
        raise RerankError(
            f"rerank returned {len(scores)} scores for {len(candidates)} candidates"
        )

    # Robust CE normalization avoids a single extreme logit flattening all
    # useful score differences. The RRF prior uses actual merge evidence;
    # exhaustive CE-only additions correctly receive a zero prior.
    norm_ce = _robust_minmax(scores)
    norm_rrf = _robust_minmax([float(c.rrf_score) for c in candidates])
    alpha = float(blend_rrf)
    blended = [
        (1.0 - alpha) * ce + alpha * rr for ce, rr in zip(norm_ce, norm_rrf, strict=True)
    ]

    scored: list[tuple[Candidate, float, float]] = [
        (cand, float(raw), float(blend))
        for cand, raw, blend in zip(candidates, scores, blended, strict=True)
    ]
    by_blend = sorted(
        scored,
        key=lambda row: (-row[2], -row[1], row[0].standard_code),
    )
    score_by_code = {c.standard_code: (raw, blend) for c, raw, blend in scored}
    rank_by_code = {
        cand.standard_code: rank
        for rank, (cand, _raw, _blend) in enumerate(by_blend, start=1)
    }

    # Preserve = must appear in the final top_n set (not pinned in raw RRF order).
    must_keep_order = [
        c.standard_code
        for c in candidates[: min(int(preserve_rrf_top), len(candidates))]
    ]
    must_keep = set(must_keep_order)
    selected_codes: list[str] = []
    seen: set[str] = set()

    # First take best blended scores.
    for cand, _raw, _blend in by_blend:
        if len(selected_codes) >= top_n:
            break
        if cand.standard_code in seen:
            continue
        selected_codes.append(cand.standard_code)
        seen.add(cand.standard_code)

    # If a preserved RRF hit was crowded out, swap in the worst blended slot.
    for code in must_keep_order:
        if code in seen or len(selected_codes) < top_n:
            if code not in seen and len(selected_codes) < top_n:
                selected_codes.append(code)
                seen.add(code)
            continue
        # Replace lowest-blend selected item that is not itself preserved.
        replace_at = None
        worst_blend = None
        for i, sel in enumerate(selected_codes):
            if sel in must_keep:
                continue
            b = score_by_code[sel][1]
            if worst_blend is None or b < worst_blend:
                worst_blend = b
                replace_at = i
        if replace_at is not None:
            old = selected_codes[replace_at]
            selected_codes[replace_at] = code
            seen.discard(old)
            seen.add(code)

    # Final order: blended score desc (enterprise judge still sees best first).
    cand_by_code = {c.standard_code: c for c in candidates}
    ordered = sorted(
        selected_codes,
        key=lambda code: (
            -score_by_code[code][1],
            -score_by_code[code][0],
            code,
        ),
    )
    selected: list[Candidate] = []
    for code in ordered:
        cand = cand_by_code[code]
        raw = score_by_code[code][0]
        selected.append(
            Candidate(
                standard_code=cand.standard_code,
                text=cand.text,
                rrf_score=cand.rrf_score,
                dense_rank=cand.dense_rank,
                bm25_rank=cand.bm25_rank,
                rrf_rank=cand.rrf_rank,
                dense_score=cand.dense_score,
                bm25_score=cand.bm25_score,
                rerank_score=float(raw),
                blended_score=float(score_by_code[code][1]),
                rerank_rank=rank_by_code[code],
                final_rank=cand.final_rank,
                query_hits=cand.query_hits,
                query_hit_weight=cand.query_hit_weight,
                arm_hits=list(cand.arm_hits),
                domain_primary=cand.domain_primary,
                parent_code=cand.parent_code,
                label=cand.label,
                level=cand.level,
                grade=cand.grade,
            )
        )
    return selected


__all__ = [
    "DEFAULT_RERANK_MODEL",
    "DEFAULT_RERANK_DOCUMENT_CHARS",
    "DEFAULT_RERANK_QUERY_CHARS",
    "DEFAULT_RERANK_TOP_N",
    "RerankError",
    "cross_encoder_scores",
    "format_rerank_document",
    "format_rerank_query",
    "rerank_candidates",
    "resolve_rerank_model",
]
