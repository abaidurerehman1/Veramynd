"""OpenAI dense embeddings + Qdrant upsert for normalized standards.

Uses ``text-embedding-3-large`` (best OpenAI embedding model). Standards embed
into ``veramynd_standards`` from each leaf retrieval text.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
import uuid
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable
from urllib.parse import urlparse

from ..normalize.llm import (
    format_non_retryable_openai_error,
    is_non_retryable_openai_error,
    load_dotenv,
    openai_api_key,
)
from ..paths import resolve_package_relative
from ..text_utils import atomic_write_text
from .standard_io import EmbeddableStandard, load_embeddable_standards

if TYPE_CHECKING:
    from ..config import EmbedConfig

DEFAULT_EMBEDDING_MODEL = "text-embedding-3-large"
DEFAULT_DIMENSIONS = 3072  # full text-embedding-3-large quality
DEFAULT_STANDARDS_COLLECTION = "veramynd_standards"
DEFAULT_QDRANT_PATH = ".qdrant_data"
EMBED_SCHEMA_VERSION = "1.0-embed-qdrant"
STANDARDS_EMBED_SCHEMA_VERSION = "1.0-embed-standards-qdrant"
PROGRESS_NAME = "embed_progress.json"
MANIFEST_NAME = "embed_manifest.json"
STANDARDS_PROGRESS_NAME = "embed_standards_progress.json"
STANDARDS_MANIFEST_NAME = "embed_standards_manifest.json"

# OpenAI embedding input hard limit for text-embedding-3-*.
_MAX_INPUT_TOKENS = 8191
# Conservative chars→tokens for preflight (tiktoken not required).
_CHARS_PER_TOKEN = 3.5
# Batch by approximate tokens to stay under request limits.
_MAX_BATCH_TOKENS = 80_000
_MAX_BATCH_ITEMS = 64
_NAMESPACE = uuid.UUID("6ba7b810-9dad-11d1-80b4-00c04fd430c8")  # URL namespace
# Path-mode Qdrant allows only one open client per storage folder.
_QDRANT_CLIENT_CACHE: dict[str, Any] = {}


class EmbedError(RuntimeError):
    pass


def _assert_nonzero_vectors(
    vectors: list[list[float]],
    *,
    labels: list[str] | None = None,
) -> None:
    """Fail loud if any embedding is all zeros (breaks Cosine dense retrieval)."""
    for i, vec in enumerate(vectors):
        if not vec:
            label = (labels[i] if labels and i < len(labels) else f"index {i}")
            raise EmbedError(f"{label}: empty embedding vector")
        if all(float(x) == 0.0 for x in vec):
            label = (labels[i] if labels and i < len(labels) else f"index {i}")
            raise EmbedError(
                f"{label}: all-zero embedding vector "
                f"(dim={len(vec)}); refusing to upsert — dense Cosine scores "
                "would be 0.0. Re-run embed after fixing the embedding source."
            )


def _assert_qdrant_vectors_nonzero(
    client: Any,
    collection: str,
    *,
    sample: int = 5,
) -> None:
    """Post-upsert sanity check: sample stored vectors must be non-zero."""
    points, _next = client.scroll(
        collection_name=collection,
        limit=max(1, sample),
        with_vectors=True,
        with_payload=False,
    )
    if not points:
        raise EmbedError(f"collection {collection!r}: no points after upsert")
    for p in points:
        vec = p.vector
        if isinstance(vec, dict):
            vec = next(iter(vec.values()), None) if vec else None
        if not vec or all(float(x) == 0.0 for x in vec):
            raise EmbedError(
                f"collection {collection!r}: stored vector is all zeros "
                f"(point id={p.id}). Dense retrieval will score 0.0 — "
                "check Qdrant storage / re-run with --recreate."
            )


def resolve_embedding_model(explicit: str | None = None, cfg: "EmbedConfig | None" = None) -> str:
    load_dotenv()
    if explicit and explicit.strip():
        return explicit.strip()
    if cfg and cfg.embedding_model and cfg.embedding_model.strip():
        return cfg.embedding_model.strip()
    env = (os.environ.get("OPENAI_EMBEDDING_MODEL") or "").strip()
    return env or DEFAULT_EMBEDDING_MODEL


def resolve_qdrant_settings(
    *,
    url: str | None = None,
    api_key: str | None = None,
    path: str | None = None,
    collection: str | None = None,
    cfg: "EmbedConfig | None" = None,
) -> dict[str, Any]:
    load_dotenv()
    resolved_url = (
        url or (cfg.qdrant_url if cfg else None) or os.environ.get("QDRANT_URL") or ""
    ).strip() or None
    resolved_key = (
        api_key or (cfg.qdrant_api_key if cfg else None) or os.environ.get("QDRANT_API_KEY") or ""
    ).strip() or None
    if resolved_key and resolved_url:
        # Schemeless URLs ("host:6333") default to http in qdrant-client, and
        # urlparse would misread "host:6333" as scheme="host" — normalize so
        # anything that isn't explicitly https counts as plaintext.
        probe = resolved_url if "://" in resolved_url else f"http://{resolved_url}"
        parsed = urlparse(probe)
        host = (parsed.hostname or "").lower()
        if parsed.scheme != "https" and host not in {"localhost", "127.0.0.1", "::1"}:
            allow_insecure = (cfg.qdrant_allow_insecure if cfg else False) or (
                os.environ.get("QDRANT_ALLOW_INSECURE") or ""
            ).strip() == "1"
            if not allow_insecure:
                raise EmbedError(
                    f"refusing to send the Qdrant API key over plaintext http "
                    f"to {host!r} ({resolved_url}). Use https://, or set "
                    f"QDRANT_ALLOW_INSECURE=1 to override (not for production)."
                )
            print(
                f"WARNING: QDRANT_ALLOW_INSECURE=1 — sending the Qdrant API key "
                f"over plaintext http to {host!r}",
                flush=True,
            )
    env_path = (os.environ.get("QDRANT_PATH") or "").strip()
    cfg_path = (cfg.qdrant_path if cfg else None) or ""
    raw_path = (path or cfg_path or env_path or DEFAULT_QDRANT_PATH).strip()
    resolved_path = str(resolve_package_relative(raw_path))
    resolved_collection = (
        (
            collection
            or (cfg.qdrant_collection if cfg else None)
            or (cfg.qdrant_standards_collection if cfg else None)
            or os.environ.get("QDRANT_STANDARDS_COLLECTION")
            or DEFAULT_STANDARDS_COLLECTION
        ).strip()
        or DEFAULT_STANDARDS_COLLECTION
    )
    # Fail loud on dual-backend ambiguity: URL always wins when set.
    if resolved_url and (path or cfg_path or env_path):
        print(
            "WARNING: QDRANT_URL is set — using Docker/HTTP Qdrant and ignoring "
            f"QDRANT_PATH ({resolved_path}). Unset QDRANT_URL to use local path "
            "mode, or unset QDRANT_PATH to silence this warning.",
            flush=True,
        )
    return {
        "url": resolved_url,
        "api_key": resolved_key,
        "path": resolved_path,
        "collection": resolved_collection,
    }


def resolve_standards_qdrant_settings(
    *,
    url: str | None = None,
    api_key: str | None = None,
    path: str | None = None,
    collection: str | None = None,
    cfg: "EmbedConfig | None" = None,
) -> dict[str, Any]:
    """Like ``resolve_qdrant_settings`` but defaults to standards collection.

    Intentionally ignores ``QDRANT_COLLECTION``/``cfg.qdrant_collection`` so
    standards embed uses the standards collection unless overridden via
    explicit ``collection``, ``cfg.qdrant_standards_collection``,
    or ``QDRANT_STANDARDS_COLLECTION``.
    """
    load_dotenv()
    base = resolve_qdrant_settings(url=url, api_key=api_key, path=path, collection=None, cfg=cfg)
    resolved_collection = (
        (
            collection
            or (cfg.qdrant_standards_collection if cfg else None)
            or os.environ.get("QDRANT_STANDARDS_COLLECTION")
            or DEFAULT_STANDARDS_COLLECTION
        ).strip()
        or DEFAULT_STANDARDS_COLLECTION
    )
    base["collection"] = resolved_collection
    return base


def point_id_for_key(key: str) -> str:
    """Deterministic UUID string for Qdrant point id (stable across re-runs)."""
    return str(uuid.uuid5(_NAMESPACE, key))


def point_id_for_standard(standard_code: str) -> str:
    """Deterministic UUID for a standard leaf (``std:{code}`` namespace key)."""
    return point_id_for_key(f"std:{standard_code}")


def _estimate_tokens(text: str) -> int:
    return max(1, int(len(text) / _CHARS_PER_TOKEN) + 1)


def _item_label(item: Any) -> str:
    if getattr(item, "standard_code", None):
        return str(item.standard_code)
    return repr(item)


def _validate_text_lengths(items: list[Any]) -> None:
    for c in items:
        est = _estimate_tokens(c.text)
        if est > _MAX_INPUT_TOKENS:
            raise EmbedError(
                f"{_item_label(c)!r} ~{est} tokens exceeds OpenAI embedding "
                f"limit ({_MAX_INPUT_TOKENS}); shorten text before embedding"
            )


def _iter_batches(items: list[Any]) -> list[list[Any]]:
    batches: list[list[Any]] = []
    current: list[Any] = []
    tok = 0
    for c in items:
        c_tok = _estimate_tokens(c.text)
        if current and (
            len(current) >= _MAX_BATCH_ITEMS or tok + c_tok > _MAX_BATCH_TOKENS
        ):
            batches.append(current)
            current = []
            tok = 0
        current.append(c)
        tok += c_tok
    if current:
        batches.append(current)
    return batches


def openai_embed_texts(
    texts: list[str],
    *,
    model: str,
    dimensions: int = DEFAULT_DIMENSIONS,
    api_key: str | None = None,
    max_retries: int = 6,
) -> list[list[float]]:
    """Call OpenAI Embeddings API; returns vectors aligned to ``texts``."""
    if not texts:
        return []
    try:
        from openai import OpenAI
        from openai import APIConnectionError, APIStatusError, RateLimitError
    except ImportError as e:
        raise EmbedError(
            "openai package required. Install with: pip install -e '.[embed]'"
        ) from e

    client = OpenAI(api_key=openai_api_key(api_key))
    delay = 1.0
    last_err: Exception | None = None
    for attempt in range(max_retries):
        try:
            resp = client.embeddings.create(
                model=model,
                input=texts,
                dimensions=dimensions,
            )
            try:
                from veramynd_parser.normalize.llm import record_openai_usage

                record_openai_usage(resp, model)
            except Exception:  # noqa: BLE001 — never fail embed on usage bookkeeping
                pass
            by_index = {item.index: item.embedding for item in resp.data}
            if len(by_index) != len(texts):
                raise EmbedError(
                    f"OpenAI returned {len(by_index)} embeddings for {len(texts)} inputs"
                )
            vectors: list[list[float]] = []
            for i in range(len(texts)):
                if i not in by_index:
                    raise EmbedError(f"OpenAI response missing embedding index {i}")
                vec = by_index[i]
                if len(vec) != dimensions:
                    raise EmbedError(
                        f"embedding dim {len(vec)} != expected {dimensions} "
                        f"(model={model})"
                    )
                vectors.append(vec)
            return vectors
        except RateLimitError as e:
            if is_non_retryable_openai_error(e):
                raise EmbedError(format_non_retryable_openai_error(e)) from e
            last_err = e
            if attempt + 1 >= max_retries:
                break
            time.sleep(delay)
            delay = min(delay * 2, 60.0)
        except APIConnectionError as e:
            last_err = e
            if attempt + 1 >= max_retries:
                break
            time.sleep(delay)
            delay = min(delay * 2, 60.0)
        except APIStatusError as e:
            last_err = e
            if is_non_retryable_openai_error(e):
                raise EmbedError(format_non_retryable_openai_error(e)) from e
            # Retry transient 5xx only (and retryable 429s that arrived as APIStatusError).
            status = getattr(e, "status_code", None)
            retryable = status == 429 or (isinstance(status, int) and status >= 500)
            if not retryable or attempt + 1 >= max_retries:
                raise EmbedError(f"OpenAI embeddings API error: {e}") from e
            time.sleep(delay)
            delay = min(delay * 2, 60.0)
    raise EmbedError(f"OpenAI embeddings failed after retries: {last_err}")


def _make_qdrant_client(*, url: str | None, api_key: str | None, path: str):
    """Return a process-cached Qdrant client (path mode cannot open twice)."""
    try:
        from qdrant_client import QdrantClient
    except ImportError as e:
        raise EmbedError(
            "qdrant-client required. Install with: pip install -e '.[embed]'"
        ) from e

    if url:
        cache_key = f"url:{url}|key:{api_key or ''}"
    elif path in {":memory:", "memory"}:
        cache_key = "memory"
    else:
        cache_key = f"path:{Path(path).resolve()}"

    hit = _QDRANT_CLIENT_CACHE.get(cache_key)
    if hit is not None:
        return hit

    if url:
        client = QdrantClient(url=url, api_key=api_key, prefer_grpc=False)
    elif path in {":memory:", "memory"}:
        client = QdrantClient(location=":memory:")
    else:
        Path(path).mkdir(parents=True, exist_ok=True)
        client = QdrantClient(path=path)

    _QDRANT_CLIENT_CACHE[cache_key] = client
    return client


def ensure_collection(
    client: Any,
    collection: str,
    *,
    dimensions: int,
    recreate: bool = False,
) -> None:
    from qdrant_client.http import models as qm

    exists = client.collection_exists(collection)
    if exists and recreate:
        client.delete_collection(collection)
        exists = False
    if exists:
        info = client.get_collection(collection)
        # qdrant-client versions differ slightly in attribute layout.
        vectors = info.config.params.vectors
        size = getattr(vectors, "size", None)
        if size is None and isinstance(vectors, dict):
            # named vectors — we use unnamed single vector
            raise EmbedError(
                f"collection {collection!r} uses named vectors; "
                "expected a single unnamed dense vector"
            )
        if size != dimensions:
            raise EmbedError(
                f"collection {collection!r} has vector size {size}, "
                f"but model produces {dimensions}. Re-run with --recreate."
            )
        return

    client.create_collection(
        collection_name=collection,
        vectors_config=qm.VectorParams(size=dimensions, distance=qm.Distance.COSINE),
    )


def delete_points_by_payload_match(
    client: Any,
    collection: str,
    *,
    key: str,
    values: set[str],
) -> None:
    """Delete all points whose payload ``key`` is in ``values`` (partial refresh)."""
    from qdrant_client.http import models as qm

    if not values or not client.collection_exists(collection):
        return
    client.delete(
        collection_name=collection,
        points_selector=qm.FilterSelector(
            filter=qm.Filter(
                must=[
                    qm.FieldCondition(
                        key=key,
                        match=qm.MatchAny(any=sorted(values)),
                    )
                ]
            )
        ),
        wait=True,
    )


def delete_points_by_ids(client: Any, collection: str, point_ids: list[str]) -> None:
    """Delete points by Qdrant point id (batched)."""
    if not point_ids or not client.collection_exists(collection):
        return
    for i in range(0, len(point_ids), 256):
        client.delete(
            collection_name=collection,
            points_selector=point_ids[i : i + 256],
            wait=True,
        )


def scroll_embed_payload_index(
    client: Any,
    collection: str,
    *,
    id_key: str,
) -> dict[str, dict[str, Any]]:
    """Map payload id → {content_hash, model_id, dimensions, point_id}."""
    out: dict[str, dict[str, Any]] = {}
    if not client.collection_exists(collection):
        return out
    offset = None
    while True:
        points, offset = client.scroll(
            collection_name=collection,
            limit=256,
            offset=offset,
            with_payload=True,
            with_vectors=False,
        )
        for p in points:
            payload = p.payload or {}
            kid = (payload.get(id_key) or "").strip()
            if not kid:
                continue
            out[kid] = {
                "content_hash": (payload.get("content_hash") or "").strip(),
                "model_id": (payload.get("model_id") or "").strip(),
                "dimensions": payload.get("dimensions"),
                "point_id": p.id,
            }
        if offset is None:
            break
    return out


def _needs_reembed(
    item_id: str,
    content_hash: str,
    *,
    existing: dict[str, dict[str, Any]],
    model_id: str,
    dimensions: int,
) -> bool:
    hit = existing.get(item_id)
    if hit is None:
        return True
    if hit.get("content_hash") != content_hash:
        return True
    if hit.get("model_id") != model_id:
        return True
    if hit.get("dimensions") != dimensions:
        return True
    return False


def upsert_standards(
    client: Any,
    collection: str,
    standards: list[EmbeddableStandard],
    vectors: list[list[float]],
    *,
    model_id: str,
    dimensions: int,
    batch_size: int = 64,
) -> int:
    from qdrant_client.http import models as qm

    if len(standards) != len(vectors):
        raise EmbedError("standards/vectors length mismatch")

    points: list[qm.PointStruct] = []
    for std, vec in zip(standards, vectors, strict=True):
        if len(vec) != dimensions:
            raise EmbedError(
                f"{std.standard_code}: vector length {len(vec)} != {dimensions}"
            )
        payload = {
            "standard_code": std.standard_code,
            "family": "standard",
            "level": std.level,
            "grade": std.grade,
            "framework": std.framework,
            "label": std.label,
            "domain_primary": std.domain_primary,
            "content_hash": std.content_hash,
            "text": std.text,
            "metadata": std.metadata,
            "model_id": model_id,
            "dimensions": dimensions,
        }
        points.append(
            qm.PointStruct(
                id=point_id_for_standard(std.standard_code),
                vector=vec,
                payload=payload,
            )
        )

    written = 0
    for i in range(0, len(points), batch_size):
        batch = points[i : i + batch_size]
        client.upsert(collection_name=collection, points=batch, wait=True)
        written += len(batch)
    return written


def embed_standards_to_qdrant(
    standards_dir: Path | str,
    out_dir: Path | str,
    *,
    model: str | None = None,
    dimensions: int = DEFAULT_DIMENSIONS,
    collection: str | None = None,
    qdrant_url: str | None = None,
    qdrant_api_key: str | None = None,
    qdrant_path: str | None = None,
    recreate: bool = False,
    force: bool = False,
    openai_key: str | None = None,
    embed_fn: Callable[..., list[list[float]]] | None = None,
    qdrant_client: Any | None = None,
    codes: set[str] | None = None,
) -> dict:
    """Embed normalized **alignable leaf** standards into Qdrant.

    Uses rich retrieval text (competency, skills, verbs, keywords). Parents are
    not embedded — they remain on disk for hierarchy/UI only.

    Incremental by default (skip matching content_hash/model/dims).
    ``force`` re-embeds the selected scope. ``recreate`` rebuilds the embedding
    index for the requested scope (entire collection when no ``codes`` filter).
    """
    src = Path(standards_dir)
    dst = Path(out_dir)
    dst.mkdir(parents=True, exist_ok=True)

    model_id = resolve_embedding_model(model)
    settings = resolve_standards_qdrant_settings(
        url=qdrant_url,
        api_key=qdrant_api_key,
        path=qdrant_path,
        collection=collection,
    )
    collection_name = settings["collection"]

    standards = load_embeddable_standards(
        src, codes=codes, leaves_only=True, use_rich_text=True
    )
    if not standards:
        raise EmbedError(f"no embeddable standards found under {src}")
    _validate_text_lengths(standards)

    standards = sorted(standards, key=lambda s: s.standard_code)
    by_level: dict[str, int] = {}
    for s in standards:
        by_level[s.level or "unknown"] = by_level.get(s.level or "unknown", 0) + 1
    mode = "force" if (force or recreate) else "incremental"

    progress = {
        "schema_version": STANDARDS_EMBED_SCHEMA_VERSION,
        "status": "running",
        "mode": mode,
        "model_id": model_id,
        "dimensions": dimensions,
        "collection": collection_name,
        "total_standards": len(standards),
        "by_level": by_level,
        "upserted": 0,
        "skipped": 0,
        "failed": [],
    }
    atomic_write_text(
        dst / STANDARDS_PROGRESS_NAME, json.dumps(progress, indent=2) + "\n"
    )

    client = qdrant_client or _make_qdrant_client(
        url=settings["url"],
        api_key=settings["api_key"],
        path=settings["path"],
    )
    full_recreate = bool(recreate) and codes is None
    if recreate and codes is not None:
        print(
            "NOTE: --recreate with --code refreshes only those standards "
            "(does not delete the whole collection).",
            flush=True,
        )
    ensure_collection(
        client, collection_name, dimensions=dimensions, recreate=full_recreate
    )

    existing = (
        {}
        if full_recreate
        else scroll_embed_payload_index(
            client, collection_name, id_key="standard_code"
        )
    )
    if codes is not None and (recreate or force):
        delete_points_by_payload_match(
            client,
            collection_name,
            key="standard_code",
            values=codes,
        )
        existing = scroll_embed_payload_index(
            client, collection_name, id_key="standard_code"
        )

    if force or recreate:
        to_embed = list(standards)
    else:
        to_embed = [
            s
            for s in standards
            if _needs_reembed(
                s.standard_code,
                s.content_hash,
                existing=existing,
                model_id=model_id,
                dimensions=dimensions,
            )
        ]
    skipped_n = len(standards) - len(to_embed)

    current_ids = {s.standard_code for s in standards}
    if codes is None:
        stale_point_ids = [
            str(meta["point_id"])
            for cid, meta in existing.items()
            if cid not in current_ids
        ]
    else:
        stale_point_ids = [
            str(meta["point_id"])
            for cid, meta in existing.items()
            if cid in codes and cid not in current_ids
        ]
    if stale_point_ids and not (codes is not None and (recreate or force)):
        delete_points_by_ids(client, collection_name, stale_point_ids)
        print(f"Pruned {len(stale_point_ids)} stale standard point(s).", flush=True)

    print(
        f"Embedding {len(to_embed)}/{len(standards)} standards with {model_id} "
        f"(dim={dimensions}, skipped={skipped_n}, mode={mode}) "
        f"-> Qdrant collection {collection_name!r}",
        flush=True,
    )

    encode = embed_fn or (
        lambda texts: openai_embed_texts(
            texts,
            model=model_id,
            dimensions=dimensions,
            api_key=openai_key,
        )
    )

    upserted = 0
    if to_embed:
        all_vectors: list[list[float]] = []
        for bi, batch in enumerate(_iter_batches(to_embed), start=1):
            print(f"  OpenAI batch {bi}: {len(batch)} texts...", flush=True)
            vectors = encode([s.text for s in batch])
            if len(vectors) != len(batch):
                raise EmbedError("batch embed returned wrong count")
            _assert_nonzero_vectors(vectors, labels=[s.standard_code for s in batch])
            all_vectors.extend(vectors)

        upserted = upsert_standards(
            client,
            collection_name,
            to_embed,
            all_vectors,
            model_id=model_id,
            dimensions=dimensions,
        )
        if upserted != len(to_embed):
            raise EmbedError(f"upserted {upserted} != {len(to_embed)} standards")

    corpus_hash = hashlib.sha256(
        "\n".join(f"{s.standard_code}:{s.content_hash}" for s in standards).encode(
            "utf-8"
        )
    ).hexdigest()

    count = client.count(collection_name, exact=True).count
    if codes is None and count < len(standards):
        raise EmbedError(
            f"Qdrant collection count {count} < corpus {len(standards)} "
            "(collection may have been partially written)"
        )
    if codes is None and count > len(standards):
        raise EmbedError(
            f"Qdrant collection count {count} > corpus {len(standards)} — "
            "stale points remain from a prior corpus. Re-run with --recreate."
        )
    if count > 0:
        _assert_qdrant_vectors_nonzero(client, collection_name)

    backend = "url" if settings["url"] else "local_path"
    manifest = {
        "schema_version": STANDARDS_EMBED_SCHEMA_VERSION,
        "mode": mode,
        "model_id": model_id,
        "dimensions": dimensions,
        "distance": "Cosine",
        "collection": collection_name,
        "qdrant_backend": backend,
        "qdrant_url": settings["url"],
        "qdrant_path": None if settings["url"] else settings["path"],
        "by_level": by_level,
        "total_vectors": len(standards),
        "upserted": upserted,
        "skipped": skipped_n,
        "qdrant_point_count": count,
        "corpus_hash": corpus_hash,
        "failed": [],
        "source_standards_dir": str(src),
        "codes_filter": sorted(codes) if codes else None,
        "note": "incremental skips matching content_hash; one vector per leaf via embed_text",
    }
    atomic_write_text(
        dst / STANDARDS_MANIFEST_NAME, json.dumps(manifest, indent=2) + "\n"
    )
    progress["status"] = "complete"
    progress["upserted"] = upserted
    progress["skipped"] = skipped_n
    progress["qdrant_point_count"] = count
    atomic_write_text(
        dst / STANDARDS_PROGRESS_NAME, json.dumps(progress, indent=2) + "\n"
    )

    print(
        f"Done. upserted={upserted} skipped={skipped_n} collection={collection_name} "
        f"points={count} model={model_id} -> {dst}/",
        flush=True,
    )
    return manifest


def query_standards_by_text(
    query_text: str,
    *,
    limit: int = 8,
    model: str | None = None,
    dimensions: int = DEFAULT_DIMENSIONS,
    collection: str | None = None,
    qdrant_url: str | None = None,
    qdrant_api_key: str | None = None,
    qdrant_path: str | None = None,
    openai_key: str | None = None,
    embed_fn: Callable[..., list[list[float]]] | None = None,
    qdrant_client: Any | None = None,
) -> list[dict[str, Any]]:
    """Embed ``query_text`` and return top-k similar standards from Qdrant."""
    text = (query_text or "").strip()
    if not text:
        raise EmbedError("empty query text")

    model_id = resolve_embedding_model(model)
    settings = resolve_standards_qdrant_settings(
        url=qdrant_url,
        api_key=qdrant_api_key,
        path=qdrant_path,
        collection=collection,
    )
    collection_name = settings["collection"]
    client = qdrant_client or _make_qdrant_client(
        url=settings["url"],
        api_key=settings["api_key"],
        path=settings["path"],
    )
    if not client.collection_exists(collection_name):
        raise EmbedError(f"Qdrant collection missing: {collection_name!r}")

    encode = embed_fn or (
        lambda texts: openai_embed_texts(
            texts,
            model=model_id,
            dimensions=dimensions,
            api_key=openai_key,
        )
    )
    vectors = encode([text])
    if not vectors:
        raise EmbedError("embed returned no vector for query")
    query_vec = vectors[0]
    if not query_vec or all(float(x) == 0.0 for x in query_vec):
        raise EmbedError(
            "query embedding is all zeros — refusing dense search "
            "(check OpenAI embed / model dimensions)"
        )

    hits = client.query_points(
        collection_name=collection_name,
        query=query_vec,
        limit=limit,
        with_payload=True,
    ).points
    out: list[dict[str, Any]] = []
    skipped_missing_code = 0
    for h in hits:
        payload = h.payload or {}
        code = (payload.get("standard_code") or "").strip()
        if not code:
            skipped_missing_code += 1
            continue
        out.append(
            {
                "standard_code": code,
                "score": float(h.score) if h.score is not None else None,
                "domain_primary": payload.get("domain_primary"),
                "label": payload.get("label"),
                "level": payload.get("level"),
                "grade": payload.get("grade"),
            }
        )
    if skipped_missing_code:
        raise EmbedError(
            f"Qdrant returned {skipped_missing_code} hit(s) without standard_code; "
            "re-embed standards with --recreate"
        )
    return out


__all__ = [
    "DEFAULT_DIMENSIONS",
    "DEFAULT_EMBEDDING_MODEL",
    "DEFAULT_STANDARDS_COLLECTION",
    "EmbedError",
    "embed_standards_to_qdrant",
    "openai_embed_texts",
    "point_id_for_key",
    "point_id_for_standard",
    "query_standards_by_text",
    "resolve_embedding_model",
]
