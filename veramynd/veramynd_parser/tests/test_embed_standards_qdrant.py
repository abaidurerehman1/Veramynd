"""Tests for standards → Qdrant embedding (mocked OpenAI; in-memory Qdrant)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from veramynd_parser.cli import build_parser
from veramynd_parser.embed.runner import (
    DEFAULT_EMBEDDING_MODEL,
    DEFAULT_STANDARDS_COLLECTION,
    embed_standards_to_qdrant,
    point_id_for_standard,
    query_standards_by_text,
)
from veramynd_parser.embed.standard_io import load_embeddable_standards


def _std_file(
    path: Path,
    *,
    code: str = "1.F.PA.4",
    domain: str = "Phonological Awareness",
    embed_extra: str = "syllables",
) -> None:
    data = {
        "schema_version": "1.0-std",
        "standard_code": code,
        "level": "standard",
        "grade": 1,
        "framework": "GA ELA",
        "label": "Syllables",
        "raw_text": "Identify and manipulate syllables.",
        "parent_code": "1.F.PA",
        "domain": {"primary": domain, "secondary": []},
        "competency_statement": "Identify syllables.",
        "observable_behaviors": ["Clap syllables"],
        "pedagogy_terms": [embed_extra],
        "exact_codes": [code],
        "skill_clauses": ["Identify syllables."],
        "student_actions": {},
        "cognitive_demand": "DOK2_skills_concepts",
        "embed_text": (
            f"Standard: {code}\nDomain primary: {domain}\n"
            f"Competency: Identify syllables.\nSkills:\n- Identify syllables.\n"
            f"Pedagogy terms: {embed_extra}"
        ),
        "prompt_version": "normalize_std.v1.0",
    }
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def test_load_embeddable_standards_skips_progress(tmp_path: Path):
    _std_file(tmp_path / "1.F.PA.4.json")
    (tmp_path / "normalize_standards_progress.json").write_text(
        json.dumps({"completed": ["1.F.PA.4"], "total": 1}),
        encoding="utf-8",
    )
    rows = load_embeddable_standards(tmp_path)
    assert len(rows) == 1
    assert rows[0].standard_code == "1.F.PA.4"
    assert "syllables" in rows[0].text


def test_partial_embed_by_code_refuses_non_leaf_parent(tmp_path: Path):
    """Regression: parenthood was computed from the loaded subset, so
    --code <parent> loaded only that record, saw no children, and embedded a
    non-leaf standard as a "leaf" into the retrieval collection."""
    _std_file(tmp_path / "1.F.PA.4.json", code="1.F.PA.4")
    # Child that marks 1.F.PA.4 as a parent.
    _std_file(tmp_path / "1.F.PA.4.d.json", code="1.F.PA.4.d")
    data = json.loads((tmp_path / "1.F.PA.4.d.json").read_text(encoding="utf-8"))
    data["parent_code"] = "1.F.PA.4"
    (tmp_path / "1.F.PA.4.d.json").write_text(json.dumps(data), encoding="utf-8")

    # Full load: only the leaf survives.
    rows = load_embeddable_standards(tmp_path)
    assert [r.standard_code for r in rows] == ["1.F.PA.4.d"]

    # Partial load of the parent alone must refuse, not embed it as a leaf.
    with pytest.raises(FileNotFoundError, match="no embeddable standards"):
        load_embeddable_standards(tmp_path, codes={"1.F.PA.4"})

    # Partial load of the actual leaf still works.
    rows = load_embeddable_standards(tmp_path, codes={"1.F.PA.4.d"})
    assert [r.standard_code for r in rows] == ["1.F.PA.4.d"]


def test_qdrant_api_key_refused_over_plaintext_http(monkeypatch):
    from veramynd_parser.embed.runner import EmbedError, resolve_qdrant_settings

    monkeypatch.delenv("QDRANT_URL", raising=False)
    monkeypatch.delenv("QDRANT_API_KEY", raising=False)
    monkeypatch.delenv("QDRANT_ALLOW_INSECURE", raising=False)

    # Key over plaintext http to a non-local host: refused.
    with pytest.raises(EmbedError, match="plaintext http"):
        resolve_qdrant_settings(url="http://qdrant.example.com:6333", api_key="k")
    # Schemeless URLs default to http in qdrant-client — equally refused.
    with pytest.raises(EmbedError, match="plaintext http"):
        resolve_qdrant_settings(url="qdrant.example.com:6333", api_key="k")
    assert resolve_qdrant_settings(url="localhost:6333", api_key="k")["api_key"] == "k"
    # localhost, https, and key-less http are all fine.
    assert resolve_qdrant_settings(url="http://localhost:6333", api_key="k")["api_key"] == "k"
    assert resolve_qdrant_settings(url="https://qdrant.example.com", api_key="k")["api_key"] == "k"
    assert resolve_qdrant_settings(url="http://qdrant.example.com")["api_key"] is None
    # Explicit override escape hatch.
    monkeypatch.setenv("QDRANT_ALLOW_INSECURE", "1")
    assert (
        resolve_qdrant_settings(url="http://qdrant.example.com", api_key="k")["api_key"]
        == "k"
    )


def test_point_id_for_standard_stable():
    a = point_id_for_standard("1.F.PA.4")
    b = point_id_for_standard("1.F.PA.4")
    assert a == b
    assert a != point_id_for_standard("1.F.PA.4.d")


def test_embed_standards_to_qdrant_mocked(tmp_path: Path):
    qdrant = pytest.importorskip("qdrant_client")

    src = tmp_path / "normalize_standards"
    src.mkdir()
    _std_file(src / "1.F.PA.4.json", code="1.F.PA.4")
    _std_file(
        src / "1.L.V.1.json",
        code="1.L.V.1",
        domain="Vocabulary",
        embed_extra="word meaning",
    )
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
    manifest = embed_standards_to_qdrant(
        src,
        out,
        model="text-embedding-3-large",
        dimensions=dims,
        collection="test_standards",
        recreate=True,
        embed_fn=fake_embed,
        qdrant_client=client,
    )
    assert manifest["total_vectors"] == 2
    assert manifest["collection"] == "test_standards"
    assert manifest["qdrant_point_count"] == 2
    assert (out / "embed_standards_manifest.json").is_file()

    hit = client.retrieve(
        "test_standards",
        ids=[point_id_for_standard("1.F.PA.4")],
        with_payload=True,
    )
    assert len(hit) == 1
    assert hit[0].payload["standard_code"] == "1.F.PA.4"
    assert hit[0].payload["family"] == "standard"
    assert "Phonological" in hit[0].payload["domain_primary"]

    # Smoke query path against same in-memory collection.
    results = query_standards_by_text(
        "Identify syllables in spoken words",
        limit=2,
        dimensions=dims,
        collection="test_standards",
        embed_fn=fake_embed,
        qdrant_client=client,
    )
    assert len(results) == 2
    assert results[0]["standard_code"] in {"1.F.PA.4", "1.L.V.1"}


def test_rejects_empty_embed_text_in_thin_mode(tmp_path: Path):
    _std_file(tmp_path / "1.F.PA.4.json")
    data = json.loads((tmp_path / "1.F.PA.4.json").read_text(encoding="utf-8"))
    data["embed_text"] = "   "
    (tmp_path / "1.F.PA.4.json").write_text(json.dumps(data), encoding="utf-8")
    # Thin mode embeds embed_text directly — a blank one must fail loud.
    with pytest.raises(ValueError, match="empty retrieval/embed text"):
        load_embeddable_standards(tmp_path, use_rich_text=False)
    # Rich mode (default) rebuilds text from competency/skills/behaviors,
    # so a blank embed_text is tolerated by design.
    rows = load_embeddable_standards(tmp_path)
    assert rows and rows[0].text


def test_cli_embed_standards_wires():
    args = build_parser().parse_args(
        [
            "embed-standards",
            "output/normalize_standards",
            "--out",
            "output/embeddings",
            "--model",
            DEFAULT_EMBEDDING_MODEL,
            "--recreate",
        ]
    )
    assert args.func.__name__ == "cmd_embed_standards"
    assert args.model == DEFAULT_EMBEDDING_MODEL
    assert args.recreate is True


def test_cli_smoke_retrieve_wires():
    args = build_parser().parse_args(
        [
            "smoke-retrieve-standards",
            "--normalize-file",
            "output/normalize/G1M2U1L1.json",
            "--limit",
            "5",
        ]
    )
    assert args.func.__name__ == "cmd_smoke_retrieve_standards"
    assert args.limit == 5
    assert DEFAULT_STANDARDS_COLLECTION
