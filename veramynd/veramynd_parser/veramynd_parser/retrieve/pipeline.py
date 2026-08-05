"""Hybrid dense + BM25 retrieval with RRF, then optional cross-encoder rerank.

Architecture §8–§9: retrieve top ~30 for recall, rerank to ~8–12 for the judge.
Direction: per lesson → candidate standards.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from ..embed.runner import (
    DEFAULT_DIMENSIONS,
    DEFAULT_STANDARDS_COLLECTION,
    EmbedError,
    openai_embed_texts,
    resolve_embedding_model,
    resolve_standards_qdrant_settings,
    _make_qdrant_client,
)
from .bm25 import StandardsBm25Index
from .io import load_standard_docs
from .leaves import filter_alignable_leaves
from .models import Candidate, StandardDoc
from .rerank import DEFAULT_RERANK_TOP_N, RerankError, rerank_candidates
from .rrf import reciprocal_rank_fusion

DEFAULT_HYBRID_TOP_K = 30
DEFAULT_ARM_LIMIT = 100  # dense/BM25 over-fetch before per-query RRF (recall-first)
DEFAULT_RRF_K = 60
DEFAULT_MERGE_TOP_K = 80  # second-stage RRF pool before rerank
DEFAULT_RERANK_TOP_N_ENTERPRISE = 30
DEFAULT_RERANK_BLEND_RRF = 0.50
DEFAULT_PRESERVE_RRF_TOP = 20
DEFAULT_JUDGE_SHORTLIST_K = 20
DEFAULT_SHORTLIST_RRF_WEIGHT = 0.25
# Dense arm over-fetch so parent hits can be dropped while still filling arm_limit leaves.
DEFAULT_DENSE_OVERFETCH = 3

# Process-local BM25 reuse keyed by standards corpus fingerprint.
_BM25_CACHE: dict[str, StandardsBm25Index] = {}


def _corpus_fingerprint(docs: list[StandardDoc]) -> str:
    import hashlib

    h = hashlib.sha256()
    for d in sorted(docs, key=lambda x: x.standard_code):
        h.update(d.standard_code.encode("utf-8"))
        h.update(b"\0")
        h.update(d.text.encode("utf-8"))
        h.update(b"\0")
    return h.hexdigest()


def get_bm25_index(docs: list[StandardDoc]) -> StandardsBm25Index:
    """Reuse BM25 indexes across retrieve calls when corpus is unchanged."""
    key = _corpus_fingerprint(docs)
    hit = _BM25_CACHE.get(key)
    if hit is not None:
        return hit
    index = StandardsBm25Index(docs)
    _BM25_CACHE.clear()
    _BM25_CACHE[key] = index
    return index


class RetrieveError(RuntimeError):
    pass


def dense_search_standards(
    query: str,
    *,
    limit: int = DEFAULT_ARM_LIMIT,
    model: str | None = None,
    dimensions: int = DEFAULT_DIMENSIONS,
    collection: str | None = None,
    qdrant_url: str | None = None,
    qdrant_api_key: str | None = None,
    qdrant_path: str | None = None,
    openai_key: str | None = None,
    embed_fn: Callable[..., list[list[float]]] | None = None,
    qdrant_client: Any | None = None,
    allow_codes: set[str] | None = None,
    overfetch_factor: int = DEFAULT_DENSE_OVERFETCH,
) -> list[tuple[str, float, dict[str, Any]]]:
    """Dense cosine search over ``veramynd_standards``.

    Returns ``(standard_code, score, payload)`` ordered by score desc.

    When ``allow_codes`` is set (leaf corpus), non-leaf / unknown codes are
    dropped. The Qdrant arm over-fetches so filtering still fills ``limit``.
    """
    text = (query or "").strip()
    if not text:
        raise RetrieveError("empty query text")
    if limit < 1:
        raise ValueError(f"limit must be >= 1, got {limit}")
    if overfetch_factor < 1:
        raise ValueError(f"overfetch_factor must be >= 1, got {overfetch_factor}")

    model_id = resolve_embedding_model(model)
    settings = resolve_standards_qdrant_settings(
        url=qdrant_url,
        api_key=qdrant_api_key,
        path=qdrant_path,
        collection=collection,
    )
    collection_name = settings["collection"] or DEFAULT_STANDARDS_COLLECTION
    client = qdrant_client or _make_qdrant_client(
        url=settings["url"],
        api_key=settings["api_key"],
        path=settings["path"],
    )
    if not client.collection_exists(collection_name):
        raise RetrieveError(f"Qdrant collection missing: {collection_name!r}")

    encode = embed_fn or (
        lambda texts: openai_embed_texts(
            texts,
            model=model_id,
            dimensions=dimensions,
            api_key=openai_key,
        )
    )
    try:
        vectors = encode([text])
    except EmbedError as e:
        raise RetrieveError(str(e)) from e
    if not vectors:
        raise RetrieveError("embed returned no vector for query")
    query_vec = vectors[0]
    if not query_vec or all(float(x) == 0.0 for x in query_vec):
        raise RetrieveError(
            "query embedding is all zeros — refusing dense search "
            "(check OpenAI embed / model dimensions)"
        )

    fetch_limit = limit
    if allow_codes is not None:
        fetch_limit = min(max(limit * overfetch_factor, limit), 200)

    def _run_query() -> list[Any]:
        return client.query_points(
            collection_name=collection_name,
            query=query_vec,
            limit=fetch_limit,
            with_payload=True,
        ).points

    hits = _run_query()
    out: list[tuple[str, float, dict[str, Any]]] = []
    skipped_missing_code = 0
    for h in hits:
        payload = dict(h.payload or {})
        code = (payload.get("standard_code") or "").strip()
        if not code:
            skipped_missing_code += 1
            continue
        if allow_codes is not None and code not in allow_codes:
            continue
        score = float(h.score) if h.score is not None else 0.0
        out.append((code, score, payload))
        if len(out) >= limit:
            break
    if skipped_missing_code:
        raise RetrieveError(
            f"Qdrant returned {skipped_missing_code} hit(s) without standard_code "
            f"in collection {collection_name!r}; refuse silent recall loss — "
            "re-embed standards with --recreate"
        )
    return out


def hybrid_retrieve_standards(
    query: str,
    standards_dir: Path | str,
    *,
    top_k: int = DEFAULT_HYBRID_TOP_K,
    arm_limit: int = DEFAULT_ARM_LIMIT,
    rrf_k: int = DEFAULT_RRF_K,
    docs: list[StandardDoc] | None = None,
    bm25_index: StandardsBm25Index | None = None,
    leaves_only: bool = True,
    model: str | None = None,
    dimensions: int = DEFAULT_DIMENSIONS,
    collection: str | None = None,
    qdrant_url: str | None = None,
    qdrant_api_key: str | None = None,
    qdrant_path: str | None = None,
    openai_key: str | None = None,
    embed_fn: Callable[..., list[list[float]]] | None = None,
    qdrant_client: Any | None = None,
) -> list[Candidate]:
    """Dense + BM25 → RRF → top_k **leaf** candidates (recall stage).

    Parent / folder codes are excluded from BM25 and dense fusion so the
    judge funnel only sees alignable terminal standards.
    """
    text = (query or "").strip()
    if not text:
        raise RetrieveError("empty query text")
    if top_k < 1:
        raise ValueError(f"top_k must be >= 1, got {top_k}")

    if docs is not None:
        corpus = list(docs)
        if leaves_only:
            corpus = filter_alignable_leaves(corpus)
    else:
        corpus = load_standard_docs(standards_dir, leaves_only=leaves_only)
    if not corpus:
        raise RetrieveError(
            f"no alignable leaf standards loaded from {standards_dir}"
            + (" (leaves_only=True)" if leaves_only else "")
        )
    by_code = {d.standard_code: d for d in corpus}
    allow_codes = set(by_code)
    index = bm25_index or get_bm25_index(corpus)

    dense_hits = dense_search_standards(
        text,
        limit=arm_limit,
        model=model,
        dimensions=dimensions,
        collection=collection,
        qdrant_url=qdrant_url,
        qdrant_api_key=qdrant_api_key,
        qdrant_path=qdrant_path,
        openai_key=openai_key,
        embed_fn=embed_fn,
        qdrant_client=qdrant_client,
        allow_codes=allow_codes if leaves_only else None,
    )
    bm25_hits = index.search(text, limit=arm_limit)

    dense_ids = [code for code, _score, _p in dense_hits if code in allow_codes]
    bm25_ids = [code for code, _score in bm25_hits if code in allow_codes]
    fused = reciprocal_rank_fusion([dense_ids, bm25_ids], k=rrf_k)

    dense_rank = {code: i for i, code in enumerate(dense_ids, start=1)}
    bm25_rank = {code: i for i, code in enumerate(bm25_ids, start=1)}
    dense_score = {code: score for code, score, _p in dense_hits}
    bm25_score = {code: score for code, score in bm25_hits}
    # Prefer Qdrant payload text when present; fall back to disk embed_text.
    payload_by_code = {code: payload for code, _s, payload in dense_hits}

    out: list[Candidate] = []
    for code, rrf_score in fused:
        if code not in by_code:
            continue  # never emit parents / unknown codes
        doc = by_code[code]
        payload = payload_by_code.get(code) or {}
        text_body = (doc.text or payload.get("text") or "").strip()
        out.append(
            Candidate(
                standard_code=code,
                text=text_body,
                rrf_score=float(rrf_score),
                dense_rank=dense_rank.get(code),
                bm25_rank=bm25_rank.get(code),
                dense_score=dense_score.get(code),
                bm25_score=bm25_score.get(code),
                domain_primary=(
                    payload.get("domain_primary") or doc.domain_primary or ""
                ),
                label=payload.get("label") or doc.label or "",
                level=payload.get("level") or doc.level or "",
                grade=payload.get("grade") if "grade" in payload else doc.grade,
            )
        )
        if len(out) >= top_k:
            break
    return out


def retrieve_and_rerank(
    query: str,
    standards_dir: Path | str,
    *,
    top_k: int = DEFAULT_HYBRID_TOP_K,
    rerank_k: int = DEFAULT_RERANK_TOP_N,
    skip_rerank: bool = False,
    rerank_model: str | None = None,
    rerank_score_fn: Callable[[str, list[str]], list[float]] | None = None,
    **hybrid_kwargs: Any,
) -> list[Candidate]:
    """Hybrid RRF top_k, then cross-encoder to rerank_k (architecture funnel)."""
    candidates = hybrid_retrieve_standards(
        query, standards_dir, top_k=top_k, **hybrid_kwargs
    )
    if skip_rerank:
        return candidates
    try:
        return rerank_candidates(
            query,
            candidates,
            top_n=rerank_k,
            model_id=rerank_model,
            score_fn=rerank_score_fn,
        )
    except RerankError as e:
        raise RetrieveError(str(e)) from e


def multi_query_hybrid_retrieve(
    queries: list[str],
    standards_dir: Path | str,
    *,
    per_query_top_k: int = DEFAULT_HYBRID_TOP_K,
    merge_top_k: int = DEFAULT_MERGE_TOP_K,
    arm_limit: int = DEFAULT_ARM_LIMIT,
    rrf_k: int = DEFAULT_RRF_K,
    docs: list[StandardDoc] | None = None,
    bm25_index: StandardsBm25Index | None = None,
    leaves_only: bool = True,
    collect_diagnostics: bool = False,
    **hybrid_kwargs: Any,
) -> tuple[list[Candidate], list[dict[str, Any]]]:
    """Run hybrid retrieve per query, then fuse ranked lists with RRF.

    Returns ``(merged_candidates, per_query_diag)``.
    """
    cleaned = [(q or "").strip() for q in queries if (q or "").strip()]
    if not cleaned:
        raise RetrieveError("multi_query_hybrid_retrieve: no non-empty queries")
    if per_query_top_k < 1 or merge_top_k < 1:
        raise ValueError("per_query_top_k and merge_top_k must be >= 1")

    if docs is not None:
        corpus = list(docs)
        if leaves_only:
            corpus = filter_alignable_leaves(corpus)
    else:
        corpus = load_standard_docs(standards_dir, leaves_only=leaves_only)
    if not corpus:
        raise RetrieveError("multi_query_hybrid_retrieve: empty leaf corpus")
    index = bm25_index or get_bm25_index(corpus)
    by_code = {d.standard_code: d for d in corpus}
    allow_codes = set(by_code)

    ranked_lists: list[list[str]] = []
    best: dict[str, Candidate] = {}
    per_query_diag: list[dict[str, Any]] = []

    # Pull kwargs that dense/hybrid understand; ignore unknown safely via hybrid.
    for qi, q in enumerate(cleaned, start=1):
        # Explicit dense+BM25 for diagnostics, then same RRF as hybrid.
        dense_hits = dense_search_standards(
            q,
            limit=arm_limit,
            allow_codes=allow_codes if leaves_only else None,
            model=hybrid_kwargs.get("model"),
            dimensions=hybrid_kwargs.get("dimensions", DEFAULT_DIMENSIONS),
            collection=hybrid_kwargs.get("collection"),
            qdrant_url=hybrid_kwargs.get("qdrant_url"),
            qdrant_api_key=hybrid_kwargs.get("qdrant_api_key"),
            qdrant_path=hybrid_kwargs.get("qdrant_path"),
            openai_key=hybrid_kwargs.get("openai_key"),
            embed_fn=hybrid_kwargs.get("embed_fn"),
            qdrant_client=hybrid_kwargs.get("qdrant_client"),
        )
        bm25_hits = index.search(q, limit=arm_limit)
        dense_ids = [code for code, _s, _p in dense_hits if code in allow_codes]
        bm25_ids = [code for code, _s in bm25_hits if code in allow_codes]
        fused = reciprocal_rank_fusion([dense_ids, bm25_ids], k=rrf_k)

        dense_rank = {code: i for i, code in enumerate(dense_ids, start=1)}
        bm25_rank = {code: i for i, code in enumerate(bm25_ids, start=1)}
        dense_score = {code: score for code, score, _p in dense_hits}
        bm25_score = {code: score for code, score in bm25_hits}
        payload_by_code = {code: payload for code, _s, payload in dense_hits}

        hybrid_codes: list[str] = []
        hits: list[Candidate] = []
        for code, rrf_score in fused:
            if code not in by_code:
                continue
            doc = by_code[code]
            payload = payload_by_code.get(code) or {}
            cand = Candidate(
                standard_code=code,
                text=(doc.text or payload.get("text") or "").strip(),
                rrf_score=float(rrf_score),
                dense_rank=dense_rank.get(code),
                bm25_rank=bm25_rank.get(code),
                dense_score=dense_score.get(code),
                bm25_score=bm25_score.get(code),
                domain_primary=payload.get("domain_primary") or doc.domain_primary or "",
                label=payload.get("label") or doc.label or "",
                level=payload.get("level") or doc.level or "",
                grade=payload.get("grade") if "grade" in payload else doc.grade,
            )
            hits.append(cand)
            hybrid_codes.append(code)
            if len(hits) >= per_query_top_k:
                break

        ranked_lists.append(hybrid_codes)
        for c in hits:
            prev = best.get(c.standard_code)
            if prev is None or float(c.rrf_score) >= float(prev.rrf_score):
                best[c.standard_code] = c

        if collect_diagnostics:
            per_query_diag.append(
                {
                    "query_index": qi,
                    "dense_codes": dense_ids[:per_query_top_k],
                    "bm25_codes": bm25_ids[:per_query_top_k],
                    "hybrid_codes": hybrid_codes,
                }
            )

    fused_all = reciprocal_rank_fusion(ranked_lists, k=rrf_k)
    out: list[Candidate] = []
    for code, merge_score in fused_all:
        base = best.get(code)
        if base is None:
            continue
        out.append(
            Candidate(
                standard_code=base.standard_code,
                text=base.text,
                rrf_score=float(merge_score),
                dense_rank=base.dense_rank,
                bm25_rank=base.bm25_rank,
                dense_score=base.dense_score,
                bm25_score=base.bm25_score,
                rerank_score=None,
                domain_primary=base.domain_primary,
                label=base.label,
                level=base.level,
                grade=base.grade,
            )
        )
        if len(out) >= merge_top_k:
            break
    return out, per_query_diag


def multi_query_retrieve_and_rerank(
    queries: list[str],
    standards_dir: Path | str,
    *,
    rerank_query: str | None = None,
    per_query_top_k: int = DEFAULT_HYBRID_TOP_K,
    merge_top_k: int = DEFAULT_MERGE_TOP_K,
    arm_limit: int = DEFAULT_ARM_LIMIT,
    rerank_k: int = DEFAULT_RERANK_TOP_N_ENTERPRISE,
    skip_rerank: bool = False,
    rerank_model: str | None = None,
    rerank_score_fn: Callable[[str, list[str]], list[float]] | None = None,
    blend_rrf: float = DEFAULT_RERANK_BLEND_RRF,
    preserve_rrf_top: int = DEFAULT_PRESERVE_RRF_TOP,
    collect_diagnostics: bool = False,
    **hybrid_kwargs: Any,
) -> tuple[list[Candidate], list[Candidate], list[dict[str, Any]]]:
    """Multi-query hybrid → RRF merge → optional cross-encoder rerank.

    Returns ``(final_candidates, merged_before_rerank, per_query_diag)``.
    """
    merged, per_query_diag = multi_query_hybrid_retrieve(
        queries,
        standards_dir,
        per_query_top_k=per_query_top_k,
        merge_top_k=merge_top_k,
        arm_limit=arm_limit,
        collect_diagnostics=collect_diagnostics,
        **hybrid_kwargs,
    )
    if skip_rerank:
        return merged, merged, per_query_diag
    rq = (rerank_query or "").strip() or (queries[0] if queries else "")
    if not rq.strip():
        raise RetrieveError("multi_query_retrieve_and_rerank: empty rerank_query")
    try:
        reranked = rerank_candidates(
            rq,
            merged,
            top_n=rerank_k,
            model_id=rerank_model,
            score_fn=rerank_score_fn,
            blend_rrf=blend_rrf,
            preserve_rrf_top=preserve_rrf_top,
        )
    except RerankError as e:
        raise RetrieveError(str(e)) from e
    return reranked, merged, per_query_diag


def build_judge_shortlist(
    reranked: list[Candidate],
    merged_rrf: list[Candidate],
    *,
    top_n: int = DEFAULT_JUDGE_SHORTLIST_K,
    rrf_weight: float = DEFAULT_SHORTLIST_RRF_WEIGHT,
    k: int = DEFAULT_RRF_K,
) -> list[Candidate]:
    """Fuse reranker and first-stage RRF ranks into a cost-aware shortlist.

    The shortlist is curriculum-agnostic and does not use gold labels. It
    preserves semantic reranker ordering while giving a small prior to
    candidates supported strongly by multi-query retrieval.
    """
    if top_n < 1:
        raise ValueError(f"top_n must be >= 1, got {top_n}")
    if rrf_weight < 0:
        raise ValueError(f"rrf_weight must be >= 0, got {rrf_weight}")
    if k < 1:
        raise ValueError(f"RRF k must be >= 1, got {k}")

    by_code: dict[str, Candidate] = {}
    scores: dict[str, float] = {}
    for rank, cand in enumerate(reranked, start=1):
        by_code[cand.standard_code] = cand
        scores[cand.standard_code] = scores.get(cand.standard_code, 0.0) + 1.0 / (
            k + rank
        )
    for rank, cand in enumerate(merged_rrf, start=1):
        by_code.setdefault(cand.standard_code, cand)
        scores[cand.standard_code] = scores.get(cand.standard_code, 0.0) + (
            float(rrf_weight) / (k + rank)
        )

    ordered = sorted(scores, key=lambda code: (-scores[code], code))
    return [by_code[code] for code in ordered[:top_n]]


__all__ = [
    "DEFAULT_ARM_LIMIT",
    "DEFAULT_DENSE_OVERFETCH",
    "DEFAULT_HYBRID_TOP_K",
    "DEFAULT_JUDGE_SHORTLIST_K",
    "DEFAULT_MERGE_TOP_K",
    "DEFAULT_PRESERVE_RRF_TOP",
    "DEFAULT_RERANK_BLEND_RRF",
    "DEFAULT_RERANK_TOP_N_ENTERPRISE",
    "DEFAULT_RRF_K",
    "DEFAULT_SHORTLIST_RRF_WEIGHT",
    "RetrieveError",
    "build_judge_shortlist",
    "dense_search_standards",
    "hybrid_retrieve_standards",
    "multi_query_hybrid_retrieve",
    "multi_query_retrieve_and_rerank",
    "retrieve_and_rerank",
]
