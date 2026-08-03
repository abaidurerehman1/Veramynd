"""Tests for OpenAI→Qdrant embedding (mocked OpenAI; local Qdrant path)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from veramynd_parser.cli import build_parser
from veramynd_parser.embed.chunk_io import load_embeddable_chunks
from veramynd_parser.embed.runner import (
    DEFAULT_EMBEDDING_MODEL,
    EmbedError,
    embed_chunks_to_qdrant,
    point_id_for_chunk,
)


def _bundle(path: Path, code: str = "G1M2U1L1") -> None:
    data = {
        "schema_version": "1.0-chunk",
        "resource_id": code,
        "grade": 1,
        "module": 2,
        "unit": 1,
        "lesson": 1,
        "title": "Sample",
        "prompt_version": "normalize_ela.v2.1",
        "lesson_chunk": {
            "chunk_id": f"{code}#lesson",
            "family": "lesson",
            "resource_id": code,
            "text": "Domain primary: Comprehension\nObjective: practice noticing.",
            "content_hash": "h-lesson",
            "metadata": {"grade": 1},
        },
        "instructional_chunks": [
            {
                "chunk_id": f"{code}#Opening#A",
                "family": "instructional",
                "resource_id": code,
                "text": "[Opening A]\n- Invite students.",
                "content_hash": "h-open",
                "metadata": {"section": "Opening", "letter": "A"},
                "section": "Opening",
                "letter": "A",
                "title": "",
                "page": 1,
                "minutes": 5,
                "steps": ["Invite students."],
            }
        ],
        "evidence_pointers": [
            {
                "chunk_id": f"{code}#evidence#0",
                "family": "evidence_pointer",
                "resource_id": code,
                "text": "",
                "content_hash": "h-ev",
                "metadata": {},
                "block_chunk_id": f"{code}#Opening#A",
                "location": "Opening A",
                "quote": "Invite students.",
                "actor": "student",
                "evidence_role": "directive_prompt",
                "support": "independent",
                "supports_action": ["oral_production"],
                "qualifiers": [],
                "evidence_index": 0,
            }
        ],
    }
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def test_load_embeddable_skips_evidence(tmp_path: Path):
    by = tmp_path / "by_lesson"
    by.mkdir()
    _bundle(by / "G1M2U1L1.json")
    rows = load_embeddable_chunks(tmp_path)
    assert len(rows) == 2
    assert {r.family for r in rows} == {"lesson", "instructional"}


def test_point_id_stable():
    a = point_id_for_chunk("G1M2U1L1#lesson")
    b = point_id_for_chunk("G1M2U1L1#lesson")
    assert a == b
    assert a != point_id_for_chunk("G1M2U1L1#Opening#A")


def test_embed_to_qdrant_mocked(tmp_path: Path):
    qdrant = pytest.importorskip("qdrant_client")

    chunks_dir = tmp_path / "chunks"
    (chunks_dir / "by_lesson").mkdir(parents=True)
    _bundle(chunks_dir / "by_lesson" / "G1M2U1L1.json")
    out = tmp_path / "embeddings"

    dims = 8

    def fake_embed(texts: list[str]) -> list[list[float]]:
        out_vecs = []
        for i, t in enumerate(texts):
            v = [float((len(t) + i + j) % 17) for j in range(dims)]
            n = sum(x * x for x in v) ** 0.5 or 1.0
            out_vecs.append([x / n for x in v])
        return out_vecs

    client = qdrant.QdrantClient(location=":memory:")
    manifest = embed_chunks_to_qdrant(
        chunks_dir,
        out,
        model="text-embedding-3-large",
        dimensions=dims,
        collection="test_chunks",
        recreate=True,
        embed_fn=fake_embed,
        qdrant_client=client,
    )
    assert manifest["total_vectors"] == 2
    assert manifest["lesson_vectors"] == 1
    assert manifest["instructional_vectors"] == 1
    assert manifest["qdrant_point_count"] == 2
    assert (out / "embed_manifest.json").is_file()

    assert client.count("test_chunks", exact=True).count == 2
    hit = client.retrieve(
        "test_chunks",
        ids=[point_id_for_chunk("G1M2U1L1#lesson")],
        with_payload=True,
    )
    assert len(hit) == 1
    assert hit[0].payload["chunk_id"] == "G1M2U1L1#lesson"
    assert "Objective" in hit[0].payload["text"]


def test_rejects_empty_text(tmp_path: Path):
    by = tmp_path / "by_lesson"
    by.mkdir()
    _bundle(by / "G1M2U1L1.json")
    data = json.loads((by / "G1M2U1L1.json").read_text(encoding="utf-8"))
    data["lesson_chunk"]["text"] = "   "
    (by / "G1M2U1L1.json").write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError, match="empty text"):
        load_embeddable_chunks(tmp_path)


def test_cli_embed_chunks_wires():
    args = build_parser().parse_args(
        [
            "embed-chunks",
            "output/chunks",
            "--out",
            "output/embeddings",
            "--model",
            DEFAULT_EMBEDDING_MODEL,
            "--recreate",
        ]
    )
    assert args.func.__name__ == "cmd_embed_chunks"
    assert args.model == DEFAULT_EMBEDDING_MODEL
    assert args.recreate is True


def test_partial_recreate_does_not_wipe_other_lessons(tmp_path: Path):
    """--recreate + --resource-id must refresh only that lesson's points."""
    qdrant = pytest.importorskip("qdrant_client")

    chunks_dir = tmp_path / "chunks"
    by = chunks_dir / "by_lesson"
    by.mkdir(parents=True)
    _bundle(by / "G1M2U1L1.json", "G1M2U1L1")
    _bundle(by / "G1M2U1L2.json", "G1M2U1L2")
    out = tmp_path / "embeddings"
    dims = 8

    def fake_embed(texts: list[str]) -> list[list[float]]:
        out_vecs = []
        for i, t in enumerate(texts):
            v = [float((len(t) + i + j) % 17) for j in range(dims)]
            n = sum(x * x for x in v) ** 0.5 or 1.0
            out_vecs.append([x / n for x in v])
        return out_vecs

    client = qdrant.QdrantClient(location=":memory:")
    embed_chunks_to_qdrant(
        chunks_dir,
        out,
        dimensions=dims,
        collection="test_partial",
        recreate=True,
        embed_fn=fake_embed,
        qdrant_client=client,
    )
    assert client.count("test_partial", exact=True).count == 4

    # Drop Opening A from L1 and partial re-embed with --recreate.
    data = json.loads((by / "G1M2U1L1.json").read_text(encoding="utf-8"))
    data["instructional_chunks"] = []
    (by / "G1M2U1L1.json").write_text(json.dumps(data), encoding="utf-8")

    embed_chunks_to_qdrant(
        chunks_dir,
        out,
        dimensions=dims,
        collection="test_partial",
        recreate=True,
        embed_fn=fake_embed,
        qdrant_client=client,
        resource_ids={"G1M2U1L1"},
    )
    # L1 lesson-only (1) + L2 lesson+block (2) = 3; Opening A for L1 must be gone.
    assert client.count("test_partial", exact=True).count == 3
    assert not client.retrieve(
        "test_partial",
        ids=[point_id_for_chunk("G1M2U1L1#Opening#A")],
    )
    assert client.retrieve(
        "test_partial",
        ids=[point_id_for_chunk("G1M2U1L2#lesson")],
    )


def test_embed_incremental_skips_unchanged(tmp_path: Path):
    qdrant = pytest.importorskip("qdrant_client")

    chunks_dir = tmp_path / "chunks"
    by = chunks_dir / "by_lesson"
    by.mkdir(parents=True)
    _bundle(by / "G1M2U1L1.json", "G1M2U1L1")
    out = tmp_path / "embeddings"
    dims = 8
    calls = {"n": 0}

    def fake_embed(texts: list[str]) -> list[list[float]]:
        calls["n"] += len(texts)
        out_vecs = []
        for i, t in enumerate(texts):
            v = [float((len(t) + i + j) % 17) for j in range(dims)]
            n = sum(x * x for x in v) ** 0.5 or 1.0
            out_vecs.append([x / n for x in v])
        return out_vecs

    client = qdrant.QdrantClient(location=":memory:")
    first = embed_chunks_to_qdrant(
        chunks_dir,
        out,
        dimensions=dims,
        collection="test_incr",
        recreate=True,
        embed_fn=fake_embed,
        qdrant_client=client,
    )
    assert first["upserted"] == 2
    assert calls["n"] == 2

    second = embed_chunks_to_qdrant(
        chunks_dir,
        out,
        dimensions=dims,
        collection="test_incr",
        embed_fn=fake_embed,
        qdrant_client=client,
    )
    assert second["upserted"] == 0
    assert second["skipped"] == 2
    assert calls["n"] == 2

    forced = embed_chunks_to_qdrant(
        chunks_dir,
        out,
        dimensions=dims,
        collection="test_incr",
        force=True,
        embed_fn=fake_embed,
        qdrant_client=client,
    )
    assert forced["upserted"] == 2
    assert calls["n"] == 4
