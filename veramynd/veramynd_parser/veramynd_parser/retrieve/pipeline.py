"""Recall-first dense + BM25 + RRF retrieval with local CE rank fusion.

Focused lesson queries build a wide leaf-only union. The unchanged generic CE
is a secondary ordering signal; RRF agreement and parent-aware interleaving
protect recall before any downstream consumer applies its own budget.
"""

from __future__ import annotations

import math
import re
from dataclasses import replace
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
from .bm25 import StandardsBm25Index, tokenize
from .io import load_standard_docs
from .leaves import filter_alignable_leaves
from .models import Candidate, StandardDoc
from .rerank import DEFAULT_RERANK_TOP_N, RerankError, rerank_candidates
from .rrf import (
    MERGE_AGGREGATIONS,
    POOL_MEMBERSHIP_MODES,
    aggregate_multi_arm_rrf,
    reciprocal_rank_fusion,
    select_merge_pool,
)

DEFAULT_HYBRID_TOP_K = 60
DEFAULT_ARM_LIMIT = 200  # dense/BM25 over-fetch before per-query RRF (recall-first)
DEFAULT_RRF_K = 60
DEFAULT_MERGE_TOP_K = 200  # wide union before local CE; no GPT cost here
DEFAULT_PER_QUERY_TOP_K = 80
DEFAULT_RERANK_TOP_N_ENTERPRISE = 120
DEFAULT_RERANK_BLEND_RRF = 0.65
DEFAULT_PRESERVE_RRF_TOP = 40
DEFAULT_EXHAUSTIVE_CEILING = 200
# Keep enough final retrieval candidates for Recall@50 diagnostics. Consumers
# with a lower external budget can explicitly pass ``--judge-shortlist-k``.
DEFAULT_JUDGE_SHORTLIST_K = 50
DEFAULT_PARENT_CAP = 3
# Shortlist fusion — enterprise K-12 defaults (Batch-1 gold):
# Product cut is Recall@20 (operator/judge shortlist). First-stage multi-query
# RRF drives head order; CE is a light polish so a generic local CE cannot bury
# multi-query agreement that already ranks well in 1–20.
DEFAULT_SHORTLIST_CE_WEIGHT = 1.0
DEFAULT_SHORTLIST_RRF_WEIGHT = 10.0
# Arm/hit/skill priors stay off by default — they pull generic multi-hit leaves
# above true RRF heads under Batch-1 eval.
DEFAULT_SHORTLIST_ARM_WEIGHT = 0.0
DEFAULT_ARM_AGREE_MAX_RANK = 10
DEFAULT_QUERY_HIT_TOP_N = 12
DEFAULT_SHORTLIST_HIT_WEIGHT = 0.0
DEFAULT_SHORTLIST_DOMAIN_WEIGHT = 0.0
DEFAULT_SHORTLIST_SKILL_WEIGHT = 0.0
# Rescue off: true breadth work belongs in query arms / first-stage merge.
DEFAULT_SHORTLIST_RESCUE_SLOTS = 0
DEFAULT_SHORTLIST_RRF_HEAD_PIN = 0
DEFAULT_SHORTLIST_RRF_HEAD_WEIGHT = 0.0
# Dense/BM25-across-query channels (0 = classic hybrid-only multi-query RRF).
DEFAULT_MERGE_ARM_WEIGHT = 0.0
# Prefer best-arm agreement over pure breadth so a strong competency arm
# can place gold leaves into the shortlist head (Batch-1 R@10).
DEFAULT_MERGE_AGGREGATION = "top_k_sum"
DEFAULT_MERGE_TOP_ARMS = 3
DEFAULT_MERGE_LOG_DAMPEN_BASE = 2.0
# Depth-breadth blend: top_k_sum base + max_blend * strongest single-arm RRF
# contribution. Enterprise multi-query needs both multi-arm consensus and the
# ability for one precise competency arm (present-clearly, create-poem, etc.)
# to lift a true alignment into the product head without pure-max collapse.
DEFAULT_MERGE_MAX_BLEND = 1.0
# Pool membership: ``single`` = top by primary aggregation only;
# ``union`` also admits top merge_top_k by classic sum (ordering still primary).
DEFAULT_POOL_MEMBERSHIP_MODE = "single"
# Guarantee this many first-stage merge hits in the judge shortlist (capped
# below top_n so cross-encoder ordering still fills residual slots). Raised for
# enterprise R@50: leaves that first-stage RRF already ranks ≤40 stay visible
# after light CE polish.
DEFAULT_SHORTLIST_PRESERVE_RRF = 40
# Enterprise product cut: after score fusion, lock RRF head order so a mid-list
# CE polish cannot rewrite multi-query agreement in positions 1..head_lock.
DEFAULT_SHORTLIST_RRF_HEAD_LOCK = 12
# Mid-list CE rescue (curriculum-agnostic): when first-stage already put a leaf
# just outside the product cut and the local CE also ranks it among its head,
# add a rank prior so it can enter R@20 without scrambling RRF positions 1–12.
# Mild boost + slightly deeper CE head (≤26): strong multi-query mid-list leaves
# (e.g. predict/infer partials at RRF ~20–25) can enter the product cut without
# mid-boost=5 impostors (high CE / mid RRF) demoting true RRF~20 positives.
DEFAULT_SHORTLIST_MID_CE_BOOST = 3.0
DEFAULT_SHORTLIST_MID_RRF_MIN = 12
DEFAULT_SHORTLIST_MID_RRF_MAX = 35
DEFAULT_SHORTLIST_MID_CE_MAX = 26
# Dense arm over-fetch so parent hits can be dropped while still filling arm_limit leaves.
DEFAULT_DENSE_OVERFETCH = 3


def filter_docs_by_grade(
    docs: list[StandardDoc], grade: int | None
) -> list[StandardDoc]:
    """Restrict corpus to one grade when known (enterprise multi-grade safety)."""
    if grade is None:
        return docs
    matched = [d for d in docs if d.grade is None or int(d.grade) == int(grade)]
    if not matched:
        raise RetrieveError(
            f"no standards remain after grade filter grade={grade}"
        )
    return matched

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
    grade: int | None = None,
    overfetch_factor: int = DEFAULT_DENSE_OVERFETCH,
) -> list[tuple[str, float | None, dict[str, Any]]]:
    """Dense cosine search over ``veramynd_standards``.

    Returns ``(standard_code, score, payload)`` ordered by score desc.
    ``score`` may be ``None`` when the vector store omits it (P9: do not
    coerce missing scores to ``0.0``, which looks like a false logging zero).

    When ``allow_codes`` is set (leaf corpus), non-leaf / unknown codes are
    dropped. The Qdrant arm over-fetches so filtering still fills ``limit``.
    Optional ``grade`` applies a payload filter (plus post-filter) so
    multi-grade collections do not crowd the lesson's grade band.
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
    if allow_codes is not None or grade is not None:
        fetch_limit = min(max(limit * overfetch_factor, limit), 400)

    query_filter = None
    if grade is not None:
        from qdrant_client.http import models as qm

        query_filter = qm.Filter(
            must=[
                qm.FieldCondition(
                    key="grade",
                    match=qm.MatchValue(value=int(grade)),
                )
            ]
        )

    def _run_query() -> list[Any]:
        return client.query_points(
            collection_name=collection_name,
            query=query_vec,
            query_filter=query_filter,
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
        if grade is not None:
            raw_g = payload.get("grade")
            if raw_g is not None:
                try:
                    if int(raw_g) != int(grade):
                        continue
                except (TypeError, ValueError):
                    continue
        score = float(h.score) if h.score is not None else None
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
    grade: int | None = None,
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
    corpus = filter_docs_by_grade(corpus, grade)
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
        grade=grade,
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
    for rrf_rank, (code, rrf_score) in enumerate(fused, start=1):
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
                rrf_rank=rrf_rank,
                dense_score=dense_score.get(code),
                bm25_score=bm25_score.get(code),
                domain_primary=(
                    payload.get("domain_primary") or doc.domain_primary or ""
                ),
                parent_code=doc.parent_code,
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
    per_query_top_k: int = DEFAULT_PER_QUERY_TOP_K,
    merge_top_k: int = DEFAULT_MERGE_TOP_K,
    arm_limit: int = DEFAULT_ARM_LIMIT,
    rrf_k: int = DEFAULT_RRF_K,
    docs: list[StandardDoc] | None = None,
    bm25_index: StandardsBm25Index | None = None,
    leaves_only: bool = True,
    collect_diagnostics: bool = False,
    query_weights: list[float] | None = None,
    query_coverage_mask: list[bool] | None = None,
    query_sources: list[str] | None = None,
    merge_aggregation: str = DEFAULT_MERGE_AGGREGATION,
    merge_top_arms: int = DEFAULT_MERGE_TOP_ARMS,
    merge_log_dampen_base: float = DEFAULT_MERGE_LOG_DAMPEN_BASE,
    merge_max_blend: float = DEFAULT_MERGE_MAX_BLEND,
    pool_membership_mode: str = DEFAULT_POOL_MEMBERSHIP_MODE,
    **hybrid_kwargs: Any,
) -> tuple[list[Candidate], list[dict[str, Any]]]:
    """Run hybrid retrieve per query, then fuse ranked lists with RRF.

    Returns ``(merged_candidates, per_query_diag)``.

    ``merge_aggregation`` controls how per-query hybrid ranks are combined:
    ``sum`` (default/classic), ``max``, ``top_k_sum``, or ``log_dampened``.
    ``merge_max_blend`` optionally adds depth (strongest single arm) on top of
    that base so enterprise multi-query can honour a precise competency arm.

    ``pool_membership_mode`` controls which IDs enter the merge pool:
    ``single`` (top by primary aggregation) or ``union`` (primary top ∪ sum top).
    Ordering/scores always come from the primary aggregation.
    """
    cleaned = [(q or "").strip() for q in queries if (q or "").strip()]
    if not cleaned:
        raise RetrieveError("multi_query_hybrid_retrieve: no non-empty queries")
    if per_query_top_k < 1 or merge_top_k < 1:
        raise ValueError("per_query_top_k and merge_top_k must be >= 1")
    if query_weights is not None and len(query_weights) != len(cleaned):
        raise ValueError(
            f"query_weights length {len(query_weights)} != queries {len(cleaned)}"
        )
    if query_coverage_mask is not None and len(query_coverage_mask) != len(cleaned):
        raise ValueError(
            f"query_coverage_mask length {len(query_coverage_mask)} != queries {len(cleaned)}"
        )
    if query_sources is not None and len(query_sources) != len(cleaned):
        raise ValueError(
            f"query_sources length {len(query_sources)} != queries {len(cleaned)}"
        )
    mode = (merge_aggregation or DEFAULT_MERGE_AGGREGATION).strip().lower()
    if mode not in MERGE_AGGREGATIONS:
        raise ValueError(
            f"merge_aggregation must be one of {MERGE_AGGREGATIONS}, got {merge_aggregation!r}"
        )
    membership = (pool_membership_mode or DEFAULT_POOL_MEMBERSHIP_MODE).strip().lower()
    if membership not in POOL_MEMBERSHIP_MODES:
        raise ValueError(
            f"pool_membership_mode must be one of {POOL_MEMBERSHIP_MODES}, "
            f"got {pool_membership_mode!r}"
        )
    merge_weights = (
        [float(w) for w in query_weights]
        if query_weights is not None
        else [1.0] * len(cleaned)
    )
    coverage_mask = (
        [bool(x) for x in query_coverage_mask]
        if query_coverage_mask is not None
        else [True] * len(cleaned)
    )
    source_labels = (
        [str(s or "") for s in query_sources]
        if query_sources is not None
        else [""] * len(cleaned)
    )

    grade = hybrid_kwargs.get("grade")
    if grade is not None:
        try:
            grade = int(grade)
        except (TypeError, ValueError) as e:
            raise ValueError(f"grade must be int-compatible, got {grade!r}") from e

    if docs is not None:
        corpus = list(docs)
        if leaves_only:
            corpus = filter_alignable_leaves(corpus)
    else:
        corpus = load_standard_docs(standards_dir, leaves_only=leaves_only)
    corpus = filter_docs_by_grade(corpus, grade)
    if not corpus:
        raise RetrieveError("multi_query_hybrid_retrieve: empty leaf corpus")
    index = bm25_index or get_bm25_index(corpus)
    by_code = {d.standard_code: d for d in corpus}
    allow_codes = set(by_code)

    ranked_lists: list[list[str]] = []
    dense_lists: list[list[str]] = []
    bm25_lists: list[list[str]] = []
    best: dict[str, Candidate] = {}
    per_query_diag: list[dict[str, Any]] = []
    arm_merge_w = float(
        hybrid_kwargs.get("merge_arm_weight", DEFAULT_MERGE_ARM_WEIGHT)
    )
    arm_agree_max = int(
        hybrid_kwargs.get("arm_agree_max_rank", DEFAULT_ARM_AGREE_MAX_RANK)
    )
    query_hit_top_n = int(
        hybrid_kwargs.get("query_hit_top_n", DEFAULT_QUERY_HIT_TOP_N)
    )
    if query_hit_top_n < 1:
        raise ValueError(f"query_hit_top_n must be >= 1, got {query_hit_top_n}")

    for qi, q in enumerate(cleaned, start=1):
        dense_hits = dense_search_standards(
            q,
            limit=arm_limit,
            allow_codes=allow_codes if leaves_only else None,
            grade=grade,
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
        q_weight = float(merge_weights[qi - 1])
        source_label = source_labels[qi - 1]
        for hybrid_rank, (code, rrf_score) in enumerate(fused, start=1):
            if code not in by_code:
                continue
            doc = by_code[code]
            payload = payload_by_code.get(code) or {}
            arm_hit = {
                "query_index": qi,
                "source": source_label,
                "rank": hybrid_rank,
                "weight": q_weight,
                "contribution": float(q_weight) / float(rrf_k + hybrid_rank),
            }
            cand = Candidate(
                standard_code=code,
                text=(doc.text or payload.get("text") or "").strip(),
                rrf_score=float(rrf_score),
                dense_rank=dense_rank.get(code),
                bm25_rank=bm25_rank.get(code),
                rrf_rank=hybrid_rank,
                dense_score=dense_score.get(code),
                bm25_score=bm25_score.get(code),
                arm_hits=[arm_hit],
                domain_primary=payload.get("domain_primary") or doc.domain_primary or "",
                parent_code=doc.parent_code,
                label=payload.get("label") or doc.label or "",
                level=payload.get("level") or doc.level or "",
                grade=payload.get("grade") if "grade" in payload else doc.grade,
            )
            hits.append(cand)
            hybrid_codes.append(code)
            if len(hits) >= per_query_top_k:
                break

        ranked_lists.append(hybrid_codes)
        dense_lists.append(dense_ids[:per_query_top_k])
        bm25_lists.append(bm25_ids[:per_query_top_k])
        for c in hits:
            prev = best.get(c.standard_code)
            if prev is None:
                c.query_hits = 0
                c.query_hit_weight = 0.0
                best[c.standard_code] = c
                prev = c
            else:
                prev.arm_hits = list(prev.arm_hits) + list(c.arm_hits)
                ranks = [r for r in (prev.dense_rank, c.dense_rank) if r is not None]
                prev.dense_rank = min(ranks) if ranks else None
                ranks = [r for r in (prev.bm25_rank, c.bm25_rank) if r is not None]
                prev.bm25_rank = min(ranks) if ranks else None
                prev.dense_score = max(
                    [s for s in (prev.dense_score, c.dense_score) if s is not None],
                    default=None,
                )
                prev.bm25_score = max(
                    [s for s in (prev.bm25_score, c.bm25_score) if s is not None],
                    default=None,
                )
                prev.rrf_score = max(float(prev.rrf_score), float(c.rrf_score))
        if coverage_mask[qi - 1]:
            for code in hybrid_codes[:query_hit_top_n]:
                prev = best.get(code)
                if prev is None:
                    continue
                prev.query_hits = int(prev.query_hits) + 1
                prev.query_hit_weight = float(prev.query_hit_weight) + q_weight

        if collect_diagnostics:
            per_query_diag.append(
                {
                    "query_index": qi,
                    "source": source_label,
                    "dense_codes": dense_ids,
                    "bm25_codes": bm25_ids,
                    "hybrid_codes": hybrid_codes,
                    "query_weight": merge_weights[qi - 1],
                }
            )

    fused_hybrid, arm_prov = aggregate_multi_arm_rrf(
        ranked_lists,
        k=rrf_k,
        weights=merge_weights,
        sources=source_labels,
        aggregation=mode,
        top_arms=merge_top_arms,
        log_dampen_base=merge_log_dampen_base,
        max_blend=float(merge_max_blend),
    )
    merge_scores: dict[str, float] = {
        code: float(score) for code, score in fused_hybrid
    }

    # Optional extras (default off). Kept only on classic ``sum`` so capped
    # aggregations are not re-breadth-biased by hit-count bonuses.
    if mode == "sum" and arm_merge_w > 0:
        fused_dense = reciprocal_rank_fusion(
            dense_lists, k=rrf_k, weights=merge_weights
        )
        fused_bm25 = reciprocal_rank_fusion(
            bm25_lists, k=rrf_k, weights=merge_weights
        )
        for code, score in fused_dense:
            merge_scores[code] = merge_scores.get(code, 0.0) + arm_merge_w * float(score)
        for code, score in fused_bm25:
            merge_scores[code] = merge_scores.get(code, 0.0) + arm_merge_w * float(score)
        for code, base in best.items():
            d = base.dense_rank
            b = base.bm25_rank
            if d is not None and b is not None:
                agree_rank = max(int(d), int(b))
                merge_scores[code] = merge_scores.get(code, 0.0) + (
                    1.5 * arm_merge_w / (rrf_k + agree_rank)
                )
                if agree_rank <= arm_agree_max:
                    merge_scores[code] += 2.5 * arm_merge_w / (rrf_k + agree_rank)
    if mode == "sum":
        for code, base in best.items():
            if float(base.query_hit_weight) > 0:
                merge_scores[code] = merge_scores.get(code, 0.0) + (
                    0.55 * float(base.query_hit_weight) / float(rrf_k)
                )

    # The arm-level extras above can score codes that never made any per-query
    # *hybrid* top-k (no ``best`` row). Those phantoms can't be emitted, and
    # letting them occupy ``merge_top_k`` slots in select_merge_pool silently
    # shrinks the pool below its budget, displacing real candidates.
    primary_ranked = sorted(
        ((code, score) for code, score in merge_scores.items() if code in best),
        key=lambda kv: (-kv[1], kv[0]),
    )
    secondary_sum_ranked: list[tuple[str, float]] | None = None
    effective_membership = membership
    if membership == "union" and mode == "sum":
        # Union with sum-primary is a no-op; keep single-path output identical.
        effective_membership = "single"
    if effective_membership == "union":
        # Reuse pure sum aggregation for membership only (no hit-weight extras).
        secondary_sum_ranked, _ = aggregate_multi_arm_rrf(
            ranked_lists,
            k=rrf_k,
            weights=merge_weights,
            sources=source_labels,
            aggregation="sum",
            top_arms=merge_top_arms,
            log_dampen_base=merge_log_dampen_base,
        )
    pool_ranked, pool_stats = select_merge_pool(
        primary_ranked,
        merge_top_k=merge_top_k,
        pool_membership_mode=effective_membership,
        secondary_sum_ranked=secondary_sum_ranked,
    )

    out: list[Candidate] = []
    for merge_rank, (code, merge_score) in enumerate(pool_ranked, start=1):
        base = best.get(code)
        if base is None:
            continue
        arm_hits = list(base.arm_hits)
        if not arm_hits and code in arm_prov:
            arm_hits = list(arm_prov[code])
            base.arm_hits = arm_hits
        out.append(
            Candidate(
                standard_code=base.standard_code,
                text=base.text,
                rrf_score=float(merge_score),
                dense_rank=base.dense_rank,
                bm25_rank=base.bm25_rank,
                rrf_rank=merge_rank,
                dense_score=base.dense_score,
                bm25_score=base.bm25_score,
                rerank_score=None,
                query_hits=int(base.query_hits),
                query_hit_weight=float(base.query_hit_weight),
                arm_hits=arm_hits,
                domain_primary=base.domain_primary,
                parent_code=base.parent_code,
                label=base.label,
                level=base.level,
                grade=base.grade,
            )
        )
    if collect_diagnostics and per_query_diag:
        per_query_diag[-1]["pool_membership"] = pool_stats
    return out, per_query_diag

def build_local_rerank_pool(
    standards_dir: Path | str,
    merged: list[Candidate],
    *,
    grade: int | None,
    exhaustive_ceiling: int = DEFAULT_EXHAUSTIVE_CEILING,
) -> tuple[list[Candidate], str]:
    """Build the local CE pool without increasing the GPT judge budget.

    For a known grade with a modest leaf corpus, score every alignable leaf.
    Otherwise retain the wide hybrid merge. The merge order remains first so
    its RRF prior is available; unseen grade leaves are appended with no prior.
    """
    if exhaustive_ceiling < 1:
        raise ValueError("exhaustive_ceiling must be >= 1")
    if grade is None:
        return list(merged), "hybrid_merge"

    corpus = filter_docs_by_grade(
        load_standard_docs(standards_dir, leaves_only=True),
        grade,
    )
    if len(corpus) > exhaustive_ceiling:
        return list(merged), "hybrid_merge"

    out = list(merged)
    seen = {c.standard_code for c in out}
    for doc in corpus:
        if doc.standard_code in seen:
            continue
        out.append(
            Candidate(
                standard_code=doc.standard_code,
                text=doc.text,
                domain_primary=doc.domain_primary,
                parent_code=doc.parent_code,
                label=doc.label,
                level=doc.level,
                grade=doc.grade,
            )
        )
        seen.add(doc.standard_code)
    return out, "grade_exhaustive"


def multi_query_retrieve_and_rerank(
    queries: list[str],
    standards_dir: Path | str,
    *,
    rerank_query: str | None = None,
    per_query_top_k: int = DEFAULT_PER_QUERY_TOP_K,
    merge_top_k: int = DEFAULT_MERGE_TOP_K,
    arm_limit: int = DEFAULT_ARM_LIMIT,
    rerank_k: int = DEFAULT_RERANK_TOP_N_ENTERPRISE,
    skip_rerank: bool = False,
    rerank_model: str | None = None,
    rerank_score_fn: Callable[[str, list[str]], list[float]] | None = None,
    blend_rrf: float = DEFAULT_RERANK_BLEND_RRF,
    preserve_rrf_top: int = DEFAULT_PRESERVE_RRF_TOP,
    exhaustive_ceiling: int = DEFAULT_EXHAUSTIVE_CEILING,
    collect_diagnostics: bool = False,
    merge_aggregation: str = DEFAULT_MERGE_AGGREGATION,
    merge_top_arms: int = DEFAULT_MERGE_TOP_ARMS,
    merge_log_dampen_base: float = DEFAULT_MERGE_LOG_DAMPEN_BASE,
    merge_max_blend: float = DEFAULT_MERGE_MAX_BLEND,
    pool_membership_mode: str = DEFAULT_POOL_MEMBERSHIP_MODE,
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
        merge_aggregation=merge_aggregation,
        merge_top_arms=merge_top_arms,
        merge_log_dampen_base=merge_log_dampen_base,
        merge_max_blend=merge_max_blend,
        pool_membership_mode=pool_membership_mode,
        **hybrid_kwargs,
    )
    rerank_pool, _pool_mode = build_local_rerank_pool(
        standards_dir,
        merged,
        grade=hybrid_kwargs.get("grade"),
        exhaustive_ceiling=exhaustive_ceiling,
    )
    if skip_rerank:
        return merged, merged, per_query_diag
    rq = (rerank_query or "").strip() or (queries[0] if queries else "")
    if not rq.strip():
        raise RetrieveError("multi_query_retrieve_and_rerank: empty rerank_query")
    try:
        reranked = rerank_candidates(
            rq,
            rerank_pool,
            top_n=rerank_k,
            model_id=rerank_model,
            score_fn=rerank_score_fn,
            blend_rrf=blend_rrf,
            preserve_rrf_top=preserve_rrf_top,
        )
    except RerankError as e:
        raise RetrieveError(str(e)) from e
    return reranked, merged, per_query_diag


def _skill_fragments(lesson_focus: str) -> list[str]:
    """Split lesson focus into clause-sized fragments for max-skill scoring.

    Concatenating objective + targets + actions into one bag dilutes rare
    anchors (e.g. \"narrative poem\") against generic instruction glue.
    """
    text = (lesson_focus or "").strip()
    if not text:
        return []
    # Prefer newline / period / semicolon / mid-dot separators when present.
    rough = re.split(r"[\n;]+|\u00b7|\s{2,}", text)
    parts: list[str] = []
    for chunk in rough:
        chunk = chunk.strip(" -.\t")
        if not chunk:
            continue
        # Further split long chunks on ", and " / sentence ends.
        for sentence in re.split(r"(?<=[.!?])\s+|\s+,\s+and\s+", chunk):
            s = sentence.strip(" -.\t")
            if len(s) >= 12:
                parts.append(s)
    if not parts:
        parts = [text]
    # Always keep full text as a fallback fragment.
    if text not in parts:
        parts.append(text)
    return parts


def _skill_overlap(lesson_focus: str, document: str) -> float:
    """Best focus-fragment coverage over the standard text (∈ [0, 1]).

    Coverage of lesson vocabulary is a stronger Top-10 prior than length-diluted
    Jaccard. Taking the max over fragments keeps rare anchors (poem, predictions,
    sun/moon observations) from being washed out by generic lesson glue.
    """
    doc_tokens = set(tokenize(document))
    if not doc_tokens:
        return 0.0
    glue = {
        "students",
        "student",
        "will",
        "can",
        "use",
        "using",
        "and",
        "the",
        "a",
        "an",
        "to",
        "of",
        "in",
        "for",
        "with",
        "about",
        "their",
        "ideas",
        "learn",
        "learning",
        "practice",
        "through",
        "close",
        "reading",
        "discussion",
        "discuss",
        "write",
        "writing",
        "story",
        "stories",
        "text",
        "texts",
        "content",
        "partner",
        "participate",
        "important",
        "events",
        "what",
        "from",
        "end",
        "do",
        "at",
        "kind",
        "helpful",
        "specific",
        "classmates",
        "peers",
        "complete",
        "sentences",
        "provide",
        "give",
        "list",
    }
    best = 0.0
    for frag in _skill_fragments(lesson_focus):
        focus = set(tokenize(frag)) - glue
        if len(focus) < 2:
            continue
        inter = len(focus & doc_tokens)
        if inter < 2 and len(focus) >= 4:
            # Need multi-token agreement when the fragment is rich.
            continue
        if inter == 0:
            continue
        cover = inter / float(len(focus))
        # Short leftover bags (1–2 tokens after glue) match too many generics;
        # discount them so multi-token lesson anchors (poem verse, sun moon)
        # dominate the max.
        if len(focus) <= 2:
            cover *= 0.25
        elif len(focus) == 3:
            cover *= 0.55
        best = max(best, min(1.0, cover))
    return best


def _domain_match_bonus(domains: set[str], cand: Candidate) -> float:
    """1.0 primary match, 0.6 secondary match, else 0."""
    if not domains:
        return 0.0
    primary = (cand.domain_primary or "").strip().lower()
    if primary and primary in domains:
        return 1.0
    text = cand.text or ""
    # Parse "Domain secondary: A, B" from leaf embed text when present.
    for line in text.splitlines():
        low = line.strip().lower()
        if low.startswith("domain secondary:"):
            secs = [s.strip() for s in low.split(":", 1)[1].split(",")]
            if any(s in domains for s in secs if s):
                return 0.6
    return 0.0


def _ranked_lists_from_arm_hits(
    pool: dict[str, Candidate],
) -> tuple[list[list[str]], list[float], list[str]]:
    """Rebuild per-query hybrid lists from Candidate.arm_hits provenance."""
    by_qi: dict[int, list[tuple[int, str, float, str]]] = {}
    for code, cand in pool.items():
        for hit in cand.arm_hits or []:
            if not isinstance(hit, dict):
                continue
            qi = int(hit.get("query_index") or 0)
            rank = int(hit.get("rank") or 0)
            if qi < 1 or rank < 1:
                continue
            weight = float(hit.get("weight") or 1.0)
            source = str(hit.get("source") or "")
            by_qi.setdefault(qi, []).append((rank, code, weight, source))

    ranked_lists: list[list[str]] = []
    weights: list[float] = []
    sources: list[str] = []
    for qi in sorted(by_qi):
        rows = sorted(by_qi[qi], key=lambda row: (row[0], row[1]))
        seen: set[str] = set()
        codes: list[str] = []
        for _rank, code, _w, _s in rows:
            if code in seen:
                continue
            seen.add(code)
            codes.append(code)
        ranked_lists.append(codes)
        weights.append(float(rows[0][2]))
        sources.append(str(rows[0][3]))
    return ranked_lists, weights, sources


def sum_ranks_from_pool(
    pool: dict[str, Candidate],
    *,
    k: int = DEFAULT_RRF_K,
) -> dict[str, int]:
    """1-based ranks under classic sum (or stored merge ranks when available).

    Prefer each candidate's ``rrf_rank`` when present so sum-rescue agrees with
    the multi-query merge that just produced this pool. Rebuilding pure sum from
    ``arm_hits`` only can disagree with weighted multi-query merge and demote
    near-cutoff fused hits.
    """
    stored = {
        code: int(cand.rrf_rank)
        for code, cand in pool.items()
        if cand.rrf_rank is not None and int(cand.rrf_rank) > 0
    }
    if len(stored) >= max(3, len(pool) // 4):
        # Dense stored ranks: use them as the rescue priority order.
        ordered = sorted(stored.items(), key=lambda kv: (kv[1], kv[0]))
        return {code: rank for rank, (code, _rr) in enumerate(ordered, start=1)}

    ranked_lists, weights, sources = _ranked_lists_from_arm_hits(pool)
    if not ranked_lists:
        return {}
    scored, _ = aggregate_multi_arm_rrf(
        ranked_lists,
        k=k,
        weights=weights,
        sources=sources,
        aggregation="sum",
    )
    return {code: rank for rank, (code, _score) in enumerate(scored, start=1)}


def apply_shortlist_rescue(
    baseline: list[Candidate],
    *,
    top_n: int,
    rescue_slots: int,
    pool: dict[str, Candidate],
    sum_ranks: dict[str, int] | None = None,
    rrf_k: int = DEFAULT_RRF_K,
) -> list[Candidate]:
    """Inject classic-sum breadth into the shortlist tail without demoting fused hits.

    Core = first ``top_n - rescue_slots`` of ``baseline`` (unchanged order).
    Rescue prefers codes that are **absent** from the fused top_n but rank well
    under classic sum (real breadth wins). Any remaining tail slots are filled
    from the fused baseline order so mid-pack fusion hits (just outside core)
    are never silently dropped when sum and fusion mostly agree.
    """
    if rescue_slots < 0:
        raise ValueError(f"rescue_slots must be >= 0, got {rescue_slots}")
    if rescue_slots == 0:
        return list(baseline[:top_n])
    # Tiny shortlists (unit tests / dry runs) silently disable rescue.
    if rescue_slots >= top_n:
        if top_n < 20:
            return list(baseline[:top_n])
        raise ValueError(
            f"rescue_slots ({rescue_slots}) must be < top_n ({top_n})"
        )

    core_n = top_n - rescue_slots
    core = list(baseline[:core_n])
    core_ids = {c.standard_code for c in core}
    fused_top = {c.standard_code for c in baseline[:top_n]}
    ranks = sum_ranks if sum_ranks is not None else sum_ranks_from_pool(pool, k=rrf_k)

    # Prefer sum-strong codes completely missing from fused top_n.
    # Cap by top_n so weak far-sum noise is never injected to fill slots.
    missing_sum = sorted(
        (
            (ranks[code], code)
            for code in pool
            if code not in fused_top
            and code in ranks
            and int(ranks[code]) <= int(top_n)
        ),
        key=lambda row: (row[0], row[1]),
    )
    rescued_codes = [code for _rank, code in missing_sum[:rescue_slots]]
    # If no true breadth misses, keep the fused shortlist intact (sum-rebuild
    # disagreement must not demote fused mid ranks ~40–50).
    if not rescued_codes:
        return [
            replace(
                cand,
                final_rank=rank,
                sum_rank=ranks.get(cand.standard_code),
                rescued_via=None,
            )
            for rank, cand in enumerate(baseline[:top_n], start=1)
        ]
    # If fewer missing injectees than slots, keep fused tail (don't demote it).
    if len(rescued_codes) < rescue_slots:
        used = core_ids | set(rescued_codes)
        for cand in baseline[core_n:top_n]:
            if cand.standard_code in used:
                continue
            rescued_codes.append(cand.standard_code)
            used.add(cand.standard_code)
            if len(rescued_codes) >= rescue_slots:
                break
    # Still short (tiny baseline / empty sum): any unused sum-ranked pool hit.
    if len(rescued_codes) < rescue_slots:
        used = core_ids | set(rescued_codes)
        fallback = sorted(
            (
                (ranks[code], code)
                for code in pool
                if code not in used and code in ranks
            ),
            key=lambda row: (row[0], row[1]),
        )
        for _rank, code in fallback:
            rescued_codes.append(code)
            if len(rescued_codes) >= rescue_slots:
                break

    out: list[Candidate] = []
    for rank, cand in enumerate(core, start=1):
        out.append(
            replace(
                cand,
                final_rank=rank,
                sum_rank=ranks.get(cand.standard_code),
                rescued_via=None,
            )
        )
    for offset, code in enumerate(rescued_codes[:rescue_slots], start=1):
        cand = pool.get(code) or next(
            (c for c in baseline if c.standard_code == code), None
        )
        if cand is None:
            continue
        via = "sum" if code not in fused_top else None
        out.append(
            replace(
                cand,
                final_rank=core_n + offset,
                sum_rank=ranks.get(code),
                rescued_via=via,
            )
        )
    # Fill any remaining holes (missing pool entries) from baseline.
    if len(out) < top_n:
        used = {c.standard_code for c in out}
        for cand in baseline:
            if cand.standard_code in used:
                continue
            out.append(
                replace(
                    cand,
                    final_rank=len(out) + 1,
                    sum_rank=ranks.get(cand.standard_code),
                    rescued_via=None,
                )
            )
            if len(out) >= top_n:
                break
    return out[:top_n]


def build_judge_shortlist(
    reranked: list[Candidate],
    merged_rrf: list[Candidate],
    *,
    top_n: int = DEFAULT_JUDGE_SHORTLIST_K,
    ce_weight: float = DEFAULT_SHORTLIST_CE_WEIGHT,
    rrf_weight: float = DEFAULT_SHORTLIST_RRF_WEIGHT,
    arm_weight: float = DEFAULT_SHORTLIST_ARM_WEIGHT,
    hit_weight: float = DEFAULT_SHORTLIST_HIT_WEIGHT,
    domain_weight: float = DEFAULT_SHORTLIST_DOMAIN_WEIGHT,
    skill_weight: float = DEFAULT_SHORTLIST_SKILL_WEIGHT,
    lesson_domains: set[str] | list[str] | None = None,
    lesson_skill_focus: str | None = None,
    arm_agree_max_rank: int = DEFAULT_ARM_AGREE_MAX_RANK,
    preserve_rrf_top: int = DEFAULT_SHORTLIST_PRESERVE_RRF,
    parent_cap: int = DEFAULT_PARENT_CAP,
    k: int = DEFAULT_RRF_K,
    rescue_slots: int = DEFAULT_SHORTLIST_RESCUE_SLOTS,
    sum_ranks: dict[str, int] | None = None,
    mid_ce_boost: float = DEFAULT_SHORTLIST_MID_CE_BOOST,
    mid_rrf_min: int = DEFAULT_SHORTLIST_MID_RRF_MIN,
    mid_rrf_max: int = DEFAULT_SHORTLIST_MID_RRF_MAX,
    mid_ce_max: int = DEFAULT_SHORTLIST_MID_CE_MAX,
    rrf_head_lock: int = DEFAULT_SHORTLIST_RRF_HEAD_LOCK,
) -> list[Candidate]:
    """Fuse reranker and first-stage RRF ranks into a cost-aware shortlist.

    The shortlist is curriculum-agnostic and does not use gold labels. First-
    stage multi-query RRF drives the product head; the local CE is a mid-list
    polish so leaves already retrieved outside the cut can enter R@20 when CE
    also ranks them among its head. ``rrf_head_lock`` freezes the first-stage
    order for positions 1..N so mid CE cannot rewrite multi-query agreement.
    """
    if top_n < 1:
        raise ValueError(f"top_n must be >= 1, got {top_n}")
    if ce_weight < 0:
        raise ValueError(f"ce_weight must be >= 0, got {ce_weight}")
    if rrf_weight < 0:
        raise ValueError(f"rrf_weight must be >= 0, got {rrf_weight}")
    if arm_weight < 0:
        raise ValueError(f"arm_weight must be >= 0, got {arm_weight}")
    if hit_weight < 0:
        raise ValueError(f"hit_weight must be >= 0, got {hit_weight}")
    if domain_weight < 0:
        raise ValueError(f"domain_weight must be >= 0, got {domain_weight}")
    if skill_weight < 0:
        raise ValueError(f"skill_weight must be >= 0, got {skill_weight}")
    if arm_agree_max_rank < 1:
        raise ValueError(f"arm_agree_max_rank must be >= 1, got {arm_agree_max_rank}")
    if preserve_rrf_top < 0:
        raise ValueError(f"preserve_rrf_top must be >= 0, got {preserve_rrf_top}")
    if parent_cap < 1:
        raise ValueError(f"parent_cap must be >= 1, got {parent_cap}")
    if k < 1:
        raise ValueError(f"RRF k must be >= 1, got {k}")
    if rescue_slots < 0:
        raise ValueError(f"rescue_slots must be >= 0, got {rescue_slots}")
    if mid_ce_boost < 0:
        raise ValueError(f"mid_ce_boost must be >= 0, got {mid_ce_boost}")
    if mid_rrf_min < 1:
        raise ValueError(f"mid_rrf_min must be >= 1, got {mid_rrf_min}")
    if mid_rrf_max < mid_rrf_min:
        raise ValueError(
            f"mid_rrf_max ({mid_rrf_max}) must be >= mid_rrf_min ({mid_rrf_min})"
        )
    if mid_ce_max < 1:
        raise ValueError(f"mid_ce_max must be >= 1, got {mid_ce_max}")
    if rrf_head_lock < 0:
        raise ValueError(f"rrf_head_lock must be >= 0, got {rrf_head_lock}")
    # Tiny shortlists (unit tests) silently disable rescue.
    if rescue_slots >= top_n:
        if top_n < 20:
            rescue_slots = 0
        else:
            raise ValueError(
                f"rescue_slots ({rescue_slots}) must be < top_n ({top_n})"
            )

    domains = {
        str(d).strip().lower()
        for d in (lesson_domains or [])
        if str(d or "").strip()
    }
    skill_focus = (lesson_skill_focus or "").strip()

    by_code: dict[str, Candidate] = {}
    scores: dict[str, float] = {}
    ce_rank_by_code: dict[str, int] = {}
    for rank, cand in enumerate(reranked, start=1):
        by_code[cand.standard_code] = cand
        ce_rank_by_code[cand.standard_code] = rank
        # Rank-based CE prior only. Continuous blended CE logits re-scramble
        # first-stage heads and hurt enterprise Recall@20 on Batch-1.
        scores[cand.standard_code] = scores.get(cand.standard_code, 0.0) + (
            float(ce_weight) / (k + rank)
        )
    arm_meta: dict[str, Candidate] = {}
    rrf_rank_by_code: dict[str, int] = {}
    for rank, cand in enumerate(merged_rrf, start=1):
        by_code.setdefault(cand.standard_code, cand)
        arm_meta[cand.standard_code] = cand
        rrf_rank_by_code[cand.standard_code] = rank
        scores[cand.standard_code] = scores.get(cand.standard_code, 0.0) + (
            float(rrf_weight) / (k + rank)
        )
        # Soft-pin strong first-stage heads so CE cannot bury them purely in
        # the top_n tail; magnitude must stay below CE head (≈ce_weight/k).
        if (
            rank <= int(DEFAULT_SHORTLIST_RRF_HEAD_PIN)
            and DEFAULT_SHORTLIST_RRF_HEAD_WEIGHT > 0
        ):
            scores[cand.standard_code] = scores.get(cand.standard_code, 0.0) + (
                float(DEFAULT_SHORTLIST_RRF_HEAD_WEIGHT) / (k + rank)
            )

    # Mid-list CE rescue: RRF already retrieved the leaf just outside the product
    # cut and CE also ranks it in its head → lift without rewriting RRF head.
    if float(mid_ce_boost) > 0:
        for code, rr in rrf_rank_by_code.items():
            ce = ce_rank_by_code.get(code)
            if ce is None:
                continue
            if mid_rrf_min <= int(rr) <= mid_rrf_max and int(ce) <= mid_ce_max:
                scores[code] = scores.get(code, 0.0) + (
                    float(mid_ce_boost) / (k + int(ce))
                )

    need_meta = (
        arm_weight > 0
        or hit_weight > 0
        or (domain_weight > 0 and domains)
        or (skill_weight > 0 and skill_focus)
    )
    if need_meta:
        for code in list(by_code):
            cand = arm_meta.get(code) or by_code[code]
            d = cand.dense_rank
            b = cand.bm25_rank
            if arm_weight > 0:
                if d is not None:
                    scores[code] = scores.get(code, 0.0) + (
                        0.5 * float(arm_weight) / (k + int(d))
                    )
                if b is not None:
                    scores[code] = scores.get(code, 0.0) + (
                        0.5 * float(arm_weight) / (k + int(b))
                    )
                if d is not None and b is not None:
                    agree = max(int(d), int(b))
                    scores[code] = scores.get(code, 0.0) + (
                        float(arm_weight) / (k + agree)
                    )
                    if agree <= arm_agree_max_rank:
                        scores[code] += 1.5 * float(arm_weight) / (k + agree)
            if hit_weight > 0 and float(cand.query_hit_weight) > 0:
                # log1p keeps multi-query popular leaves from swamping RRF/CE ranks.
                scores[code] = scores.get(code, 0.0) + (
                    float(hit_weight)
                    * math.log1p(float(cand.query_hit_weight))
                    / float(k)
                )
            if domain_weight > 0 and domains:
                scores[code] = scores.get(code, 0.0) + (
                    float(domain_weight)
                    * _domain_match_bonus(domains, cand)
                    / 10.0
                )
            if skill_weight > 0 and skill_focus:
                # Fragment-max coverage in [0,1]; scale so strong skill (~0.5+)
                # can lift mid-CE ranks into the head without drowning CE#1.
                scores[code] = scores.get(code, 0.0) + (
                    float(skill_weight) * _skill_overlap(skill_focus, cand.text)
                )

    # Prefer first-stage RRF membership for recall (enterprise R@50) while
    # leaving a residual budget for CE-only lifts (room = top_n - keep_n).
    rrf_cap = max(0, (4 * int(top_n)) // 5)  # e.g. 40 of 50
    keep_n = min(int(preserve_rrf_top), rrf_cap, len(merged_rrf))
    must_keep = [c.standard_code for c in merged_rrf[:keep_n]]
    # Also protect dual-arm agreements that noisy merge ranks may bury.
    arm_keepers = sorted(
        (
            max(int(c.dense_rank), int(c.bm25_rank)),
            c.standard_code,
        )
        for c in arm_meta.values()
        if c.dense_rank is not None
        and c.bm25_rank is not None
        and max(int(c.dense_rank), int(c.bm25_rank)) <= arm_agree_max_rank
    )
    for _agree, code in arm_keepers:
        if code in must_keep:
            continue
        must_keep.append(code)
        if len(must_keep) >= keep_n + min(10, top_n // 4):
            break

    def family(code: str) -> str:
        cand = by_code[code]
        return cand.parent_code or code.rsplit(".", 1)[0]

    ordered = sorted(scores, key=lambda code: (-scores[code], code))
    selected_set = set(ordered[:top_n])
    must_keep_set = set(must_keep)
    # Preserve strong first-stage candidates in the selected set, but do not
    # pin them ahead of better fused candidates.
    for code in must_keep:
        if code in selected_set:
            continue
        replace_code = next(
            (
                candidate
                for candidate in reversed(ordered)
                if candidate in selected_set and candidate not in must_keep_set
            ),
            None,
        )
        if replace_code is None:
            break
        selected_set.remove(replace_code)
        selected_set.add(code)

    # Diversity is a stable reordering, not a family-wide deletion. Once
    # ``parent_cap`` siblings are consecutive, defer the next sibling until a
    # different high-scoring family is emitted; every selected candidate stays.
    pending = [code for code in ordered if code in selected_set]
    selected: list[str] = []
    last_family: str | None = None
    consecutive = 0
    while pending:
        pick = 0
        if last_family is not None and consecutive >= parent_cap:
            pick = next(
                (
                    index
                    for index, code in enumerate(pending)
                    if family(code) != last_family
                ),
                0,
            )
        code = pending.pop(pick)
        current_family = family(code)
        if current_family == last_family:
            consecutive += 1
        else:
            last_family = current_family
            consecutive = 1
        selected.append(code)

    # RRF head lock: positions 1..lock keep multi-query order; mid CE polish may
    # only reorder the remainder (enterprise product head fidelity).
    lock_n = min(int(rrf_head_lock), len(selected))
    if lock_n > 0:
        head = [
            c.standard_code
            for c in merged_rrf[:lock_n]
            if c.standard_code in selected_set
        ]
        head_set = set(head)
        rest = [code for code in selected if code not in head_set]
        selected = head + rest

    baseline = [
        replace(by_code[code], final_rank=rank)
        for rank, code in enumerate(selected, start=1)
    ]
    # Prefer injecting true breadth misses only. Do not re-rank the fused
    # tail out of the shortlist when primary≈sum (that demotes near-cutoff
    # hits such as a fusion rank ~45–50 leaf just rescued by query arms).
    if int(rescue_slots) == 0:
        return baseline

    missing_ready = False
    ranks_probe = sum_ranks_from_pool(
        {c.standard_code: c for c in merged_rrf}, k=k
    ) if sum_ranks is None else sum_ranks
    fused_probe = {c.standard_code for c in baseline[:top_n]}
    for code, rank in (ranks_probe or {}).items():
        if code not in fused_probe and int(rank) <= int(top_n):
            missing_ready = True
            break
    if not missing_ready:
        # Nothing useful to inject — return fused top_n unchanged.
        return [
            replace(c, final_rank=i, sum_rank=(ranks_probe or {}).get(c.standard_code))
            for i, c in enumerate(baseline[:top_n], start=1)
        ]

    # Prefer merged candidates for arm_hits when building the rescue pool.
    pool: dict[str, Candidate] = dict(by_code)
    for code, cand in arm_meta.items():
        existing = pool.get(code)
        if existing is None:
            pool[code] = cand
            continue
        if cand.arm_hits and (
            not existing.arm_hits
            or len(cand.arm_hits) >= len(existing.arm_hits)
        ):
            pool[code] = replace(
                existing,
                arm_hits=list(cand.arm_hits),
                query_hits=cand.query_hits,
                query_hit_weight=cand.query_hit_weight,
                rrf_rank=cand.rrf_rank if cand.rrf_rank is not None else existing.rrf_rank,
                rrf_score=cand.rrf_score or existing.rrf_score,
            )

    return apply_shortlist_rescue(
        baseline,
        top_n=top_n,
        rescue_slots=int(rescue_slots),
        pool=pool,
        sum_ranks=sum_ranks,
        rrf_k=k,
    )


__all__ = [
    "DEFAULT_ARM_AGREE_MAX_RANK",
    "DEFAULT_ARM_LIMIT",
    "DEFAULT_DENSE_OVERFETCH",
    "DEFAULT_EXHAUSTIVE_CEILING",
    "DEFAULT_HYBRID_TOP_K",
    "DEFAULT_JUDGE_SHORTLIST_K",
    "DEFAULT_MERGE_AGGREGATION",
    "DEFAULT_MERGE_ARM_WEIGHT",
    "DEFAULT_MERGE_LOG_DAMPEN_BASE",
    "DEFAULT_MERGE_MAX_BLEND",
    "DEFAULT_MERGE_TOP_ARMS",
    "DEFAULT_MERGE_TOP_K",
    "DEFAULT_POOL_MEMBERSHIP_MODE",
    "DEFAULT_PER_QUERY_TOP_K",
    "DEFAULT_PARENT_CAP",
    "DEFAULT_PRESERVE_RRF_TOP",
    "DEFAULT_RERANK_BLEND_RRF",
    "DEFAULT_RERANK_TOP_N_ENTERPRISE",
    "DEFAULT_RRF_K",
    "DEFAULT_SHORTLIST_ARM_WEIGHT",
    "DEFAULT_SHORTLIST_CE_WEIGHT",
    "DEFAULT_SHORTLIST_DOMAIN_WEIGHT",
    "DEFAULT_SHORTLIST_HIT_WEIGHT",
    "DEFAULT_SHORTLIST_MID_CE_BOOST",
    "DEFAULT_SHORTLIST_MID_CE_MAX",
    "DEFAULT_SHORTLIST_MID_RRF_MAX",
    "DEFAULT_SHORTLIST_MID_RRF_MIN",
    "DEFAULT_SHORTLIST_PRESERVE_RRF",
    "DEFAULT_SHORTLIST_RESCUE_SLOTS",
    "DEFAULT_SHORTLIST_RRF_HEAD_LOCK",
    "DEFAULT_SHORTLIST_RRF_HEAD_PIN",
    "DEFAULT_SHORTLIST_RRF_HEAD_WEIGHT",
    "DEFAULT_SHORTLIST_RRF_WEIGHT",
    "DEFAULT_SHORTLIST_SKILL_WEIGHT",
    "DEFAULT_QUERY_HIT_TOP_N",
    "RetrieveError",
    "apply_shortlist_rescue",
    "build_judge_shortlist",
    "build_local_rerank_pool",
    "dense_search_standards",
    "filter_docs_by_grade",
    "get_bm25_index",
    "hybrid_retrieve_standards",
    "multi_query_hybrid_retrieve",
    "multi_query_retrieve_and_rerank",
    "retrieve_and_rerank",
    "sum_ranks_from_pool",
]
