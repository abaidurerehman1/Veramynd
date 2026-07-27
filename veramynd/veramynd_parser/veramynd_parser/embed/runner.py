"""OpenAI dense embeddings + Qdrant upsert for hierarchical chunks.

Uses ``text-embedding-3-large`` (best OpenAI embedding model). Evidence pointers
are not embedded — only ``lesson`` and ``instructional`` chunks.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
import uuid
from pathlib import Path
from typing import Any, Callable

from ..normalize.llm import load_dotenv, openai_api_key
from ..paths import resolve_package_relative
from ..text_utils import atomic_write_text
from .chunk_io import EmbeddableChunk, load_embeddable_chunks

DEFAULT_EMBEDDING_MODEL = "text-embedding-3-large"
DEFAULT_DIMENSIONS = 3072  # full text-embedding-3-large quality
DEFAULT_COLLECTION = "veramynd_chunks"
DEFAULT_QDRANT_PATH = ".qdrant_data"
EMBED_SCHEMA_VERSION = "1.0-embed-qdrant"
PROGRESS_NAME = "embed_progress.json"
MANIFEST_NAME = "embed_manifest.json"

# OpenAI embedding input hard limit for text-embedding-3-*.
_MAX_INPUT_TOKENS = 8191
# Conservative chars→tokens for preflight (tiktoken not required).
_CHARS_PER_TOKEN = 3.5
# Batch by approximate tokens to stay under request limits.
_MAX_BATCH_TOKENS = 80_000
_MAX_BATCH_ITEMS = 64
_NAMESPACE = uuid.UUID("6ba7b810-9dad-11d1-80b4-00c04fd430c8")  # URL namespace


class EmbedError(RuntimeError):
    pass


def resolve_embedding_model(explicit: str | None = None) -> str:
    load_dotenv()
    if explicit and explicit.strip():
        return explicit.strip()
    env = (os.environ.get("OPENAI_EMBEDDING_MODEL") or "").strip()
    return env or DEFAULT_EMBEDDING_MODEL


def resolve_qdrant_settings(
    *,
    url: str | None = None,
    api_key: str | None = None,
    path: str | None = None,
    collection: str | None = None,
) -> dict[str, Any]:
    load_dotenv()
    resolved_url = (url or os.environ.get("QDRANT_URL") or "").strip() or None
    resolved_key = (api_key or os.environ.get("QDRANT_API_KEY") or "").strip() or None
    raw_path = (path or os.environ.get("QDRANT_PATH") or DEFAULT_QDRANT_PATH).strip()
    resolved_path = str(resolve_package_relative(raw_path))
    resolved_collection = (
        (collection or os.environ.get("QDRANT_COLLECTION") or DEFAULT_COLLECTION).strip()
        or DEFAULT_COLLECTION
    )
    return {
        "url": resolved_url,
        "api_key": resolved_key,
        "path": resolved_path,
        "collection": resolved_collection,
    }


def point_id_for_chunk(chunk_id: str) -> str:
    """Deterministic UUID string for Qdrant point id (stable across re-runs)."""
    return str(uuid.uuid5(_NAMESPACE, chunk_id))


def _estimate_tokens(text: str) -> int:
    return max(1, int(len(text) / _CHARS_PER_TOKEN) + 1)


def _validate_chunk_lengths(chunks: list[EmbeddableChunk]) -> None:
    for c in chunks:
        est = _estimate_tokens(c.text)
        if est > _MAX_INPUT_TOKENS:
            raise EmbedError(
                f"chunk {c.chunk_id!r} ~{est} tokens exceeds OpenAI embedding "
                f"limit ({_MAX_INPUT_TOKENS}); shorten chunk text before embedding"
            )


def _iter_batches(chunks: list[EmbeddableChunk]) -> list[list[EmbeddableChunk]]:
    batches: list[list[EmbeddableChunk]] = []
    current: list[EmbeddableChunk] = []
    tok = 0
    for c in chunks:
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
        except (RateLimitError, APIConnectionError) as e:
            last_err = e
            if attempt + 1 >= max_retries:
                break
            time.sleep(delay)
            delay = min(delay * 2, 60.0)
        except APIStatusError as e:
            last_err = e
            # Retry transient 5xx only.
            if e.status_code < 500 or attempt + 1 >= max_retries:
                raise EmbedError(f"OpenAI embeddings API error: {e}") from e
            time.sleep(delay)
            delay = min(delay * 2, 60.0)
    raise EmbedError(f"OpenAI embeddings failed after retries: {last_err}")


def _make_qdrant_client(*, url: str | None, api_key: str | None, path: str):
    try:
        from qdrant_client import QdrantClient
    except ImportError as e:
        raise EmbedError(
            "qdrant-client required. Install with: pip install -e '.[embed]'"
        ) from e

    if url:
        return QdrantClient(url=url, api_key=api_key, prefer_grpc=False)
    if path in {":memory:", "memory"}:
        return QdrantClient(location=":memory:")
    Path(path).mkdir(parents=True, exist_ok=True)
    return QdrantClient(path=path)


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


def upsert_chunks(
    client: Any,
    collection: str,
    chunks: list[EmbeddableChunk],
    vectors: list[list[float]],
    *,
    model_id: str,
    dimensions: int,
    batch_size: int = 64,
) -> int:
    from qdrant_client.http import models as qm

    if len(chunks) != len(vectors):
        raise EmbedError("chunks/vectors length mismatch")

    points: list[qm.PointStruct] = []
    for chunk, vec in zip(chunks, vectors, strict=True):
        if len(vec) != dimensions:
            raise EmbedError(
                f"{chunk.chunk_id}: vector length {len(vec)} != {dimensions}"
            )
        payload = {
            "chunk_id": chunk.chunk_id,
            "family": chunk.family,
            "resource_id": chunk.resource_id,
            "content_hash": chunk.content_hash,
            "text": chunk.text,
            "metadata": chunk.metadata,
            "model_id": model_id,
            "dimensions": dimensions,
        }
        points.append(
            qm.PointStruct(
                id=point_id_for_chunk(chunk.chunk_id),
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


def embed_chunks_to_qdrant(
    chunks_dir: Path | str,
    out_dir: Path | str,
    *,
    model: str | None = None,
    dimensions: int = DEFAULT_DIMENSIONS,
    collection: str | None = None,
    qdrant_url: str | None = None,
    qdrant_api_key: str | None = None,
    qdrant_path: str | None = None,
    recreate: bool = False,
    openai_key: str | None = None,
    embed_fn: Callable[..., list[list[float]]] | None = None,
    qdrant_client: Any | None = None,
) -> dict:
    """Embed lesson+instructional chunks and upsert into Qdrant."""
    src = Path(chunks_dir)
    dst = Path(out_dir)
    dst.mkdir(parents=True, exist_ok=True)

    model_id = resolve_embedding_model(model)
    settings = resolve_qdrant_settings(
        url=qdrant_url,
        api_key=qdrant_api_key,
        path=qdrant_path,
        collection=collection,
    )
    collection_name = settings["collection"]

    chunks = load_embeddable_chunks(src)
    if not chunks:
        raise EmbedError(f"no lesson/instructional chunks found under {src}")
    _validate_chunk_lengths(chunks)

    # Stable order for reproducible manifests.
    chunks = sorted(chunks, key=lambda c: (c.family, c.resource_id, c.chunk_id))
    lesson_n = sum(1 for c in chunks if c.family == "lesson")
    block_n = sum(1 for c in chunks if c.family == "instructional")

    progress = {
        "schema_version": EMBED_SCHEMA_VERSION,
        "status": "running",
        "model_id": model_id,
        "dimensions": dimensions,
        "collection": collection_name,
        "total_chunks": len(chunks),
        "lesson_chunks": lesson_n,
        "instructional_chunks": block_n,
        "upserted": 0,
        "failed": [],
    }
    atomic_write_text(dst / PROGRESS_NAME, json.dumps(progress, indent=2) + "\n")

    print(
        f"Embedding {len(chunks)} chunks with {model_id} "
        f"(dim={dimensions}) -> Qdrant collection {collection_name!r}",
        flush=True,
    )

    client = qdrant_client or _make_qdrant_client(
        url=settings["url"],
        api_key=settings["api_key"],
        path=settings["path"],
    )
    ensure_collection(client, collection_name, dimensions=dimensions, recreate=recreate)

    encode = embed_fn or (
        lambda texts: openai_embed_texts(
            texts,
            model=model_id,
            dimensions=dimensions,
            api_key=openai_key,
        )
    )

    all_vectors: list[list[float]] = []
    for bi, batch in enumerate(_iter_batches(chunks), start=1):
        print(f"  OpenAI batch {bi}: {len(batch)} texts...", flush=True)
        vectors = encode([c.text for c in batch])
        if len(vectors) != len(batch):
            raise EmbedError("batch embed returned wrong count")
        all_vectors.extend(vectors)

    upserted = upsert_chunks(
        client,
        collection_name,
        chunks,
        all_vectors,
        model_id=model_id,
        dimensions=dimensions,
    )
    if upserted != len(chunks):
        raise EmbedError(f"upserted {upserted} != {len(chunks)} chunks")

    # Content fingerprint of embedded corpus for audit.
    corpus_hash = hashlib.sha256(
        "\n".join(f"{c.chunk_id}:{c.content_hash}" for c in chunks).encode("utf-8")
    ).hexdigest()

    count = client.count(collection_name, exact=True).count
    if count < len(chunks):
        raise EmbedError(
            f"Qdrant collection count {count} < upserted {len(chunks)} "
            "(collection may have been partially written)"
        )

    backend = "url" if settings["url"] else "local_path"
    manifest = {
        "schema_version": EMBED_SCHEMA_VERSION,
        "model_id": model_id,
        "dimensions": dimensions,
        "distance": "Cosine",
        "collection": collection_name,
        "qdrant_backend": backend,
        "qdrant_url": settings["url"],
        "qdrant_path": None if settings["url"] else settings["path"],
        "lesson_vectors": lesson_n,
        "instructional_vectors": block_n,
        "total_vectors": len(chunks),
        "qdrant_point_count": count,
        "corpus_hash": corpus_hash,
        "failed": [],
        "source_chunks_dir": str(src),
        "note": "evidence_pointer chunks are not embedded",
    }
    atomic_write_text(dst / MANIFEST_NAME, json.dumps(manifest, indent=2) + "\n")
    progress["status"] = "complete"
    progress["upserted"] = upserted
    progress["qdrant_point_count"] = count
    atomic_write_text(dst / PROGRESS_NAME, json.dumps(progress, indent=2) + "\n")

    print(
        f"Done. upserted={upserted} collection={collection_name} "
        f"points={count} model={model_id} -> {dst}/",
        flush=True,
    )
    return manifest


__all__ = [
    "DEFAULT_COLLECTION",
    "DEFAULT_DIMENSIONS",
    "DEFAULT_EMBEDDING_MODEL",
    "EmbedError",
    "embed_chunks_to_qdrant",
    "openai_embed_texts",
    "point_id_for_chunk",
    "resolve_embedding_model",
]
