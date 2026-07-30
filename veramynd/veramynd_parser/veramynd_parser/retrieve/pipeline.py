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
from .models import Candidate, StandardDoc
from .rerank import DEFAULT_RERANK_TOP_N, RerankError, rerank_candidates
from .rrf import reciprocal_rank_fusion

DEFAULT_HYBRID_TOP_K = 30
DEFAULT_ARM_LIMIT = 50  # each arm over-fetches before RRF
DEFAULT_RRF_K = 60

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
) -> list[tuple[str, float, dict[str, Any]]]:
    """Dense cosine search over ``veramynd_standards``.

    Returns ``(standard_code, score, payload)`` ordered by score desc.
    """
    text = (query or "").strip()
    if not text:
        raise RetrieveError("empty query text")
    if limit < 1:
        raise ValueError(f"limit must be >= 1, got {limit}")

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

    hits = client.query_points(
        collection_name=collection_name,
        query=query_vec,
        limit=limit,
        with_payload=True,
    ).points
    out: list[tuple[str, float, dict[str, Any]]] = []
    skipped_missing_code = 0
    for h in hits:
        payload = dict(h.payload or {})
        code = (payload.get("standard_code") or "").strip()
        if not code:
            skipped_missing_code += 1
            continue
        score = float(h.score) if h.score is not None else 0.0
        out.append((code, score, payload))
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
    """Dense + BM25 → RRF → top_k candidates (recall stage)."""
    text = (query or "").strip()
    if not text:
        raise RetrieveError("empty query text")
    if top_k < 1:
        raise ValueError(f"top_k must be >= 1, got {top_k}")

    corpus = docs if docs is not None else load_standard_docs(standards_dir)
    if not corpus:
        raise RetrieveError(f"no standards loaded from {standards_dir}")
    by_code = {d.standard_code: d for d in corpus}
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
    )
    bm25_hits = index.search(text, limit=arm_limit)

    dense_ids = [code for code, _score, _p in dense_hits]
    bm25_ids = [code for code, _score in bm25_hits]
    fused = reciprocal_rank_fusion([dense_ids, bm25_ids], k=rrf_k)

    dense_rank = {code: i for i, code in enumerate(dense_ids, start=1)}
    bm25_rank = {code: i for i, code in enumerate(bm25_ids, start=1)}
    dense_score = {code: score for code, score, _p in dense_hits}
    bm25_score = {code: score for code, score in bm25_hits}
    # Prefer Qdrant payload text when present; fall back to disk embed_text.
    payload_by_code = {code: payload for code, _s, payload in dense_hits}

    out: list[Candidate] = []
    for code, rrf_score in fused[:top_k]:
        doc = by_code.get(code)
        payload = payload_by_code.get(code) or {}
        text_body = (payload.get("text") or (doc.text if doc else "") or "").strip()
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
                    payload.get("domain_primary")
                    or (doc.domain_primary if doc else "")
                    or ""
                ),
                label=payload.get("label") or (doc.label if doc else "") or "",
                level=payload.get("level") or (doc.level if doc else "") or "",
                grade=payload.get("grade") if "grade" in payload else (doc.grade if doc else None),
            )
        )
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


__all__ = [
    "DEFAULT_ARM_LIMIT",
    "DEFAULT_HYBRID_TOP_K",
    "DEFAULT_RRF_K",
    "RetrieveError",
    "dense_search_standards",
    "hybrid_retrieve_standards",
    "retrieve_and_rerank",
]
