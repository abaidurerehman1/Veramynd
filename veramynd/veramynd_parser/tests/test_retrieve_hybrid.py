"""Tests for hybrid dense+BM25+RRF and cross-encoder rerank."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from veramynd_parser.cli import build_parser
from veramynd_parser.retrieve.bm25 import StandardsBm25Index, tokenize
from veramynd_parser.retrieve.models import Candidate, StandardDoc
from veramynd_parser.retrieve.pipeline import hybrid_retrieve_standards, retrieve_and_rerank
from veramynd_parser.retrieve.rerank import rerank_candidates
from veramynd_parser.retrieve.rrf import reciprocal_rank_fusion


def test_tokenize_keeps_dotted_codes():
    toks = tokenize("Standard 1.F.PA.4 syllables in spoken words")
    assert "1.f.pa.4" in toks
    assert "syllables" in toks


def test_rrf_prefers_items_ranked_high_in_both_lists():
    fused = reciprocal_rank_fusion(
        [
            ["A", "B", "C"],
            ["B", "A", "D"],
        ],
        k=60,
    )
    ids = [i for i, _ in fused]
    assert ids[0] in {"A", "B"}
    assert set(ids) == {"A", "B", "C", "D"}
    scores = dict(fused)
    assert scores["A"] > scores["C"]
    assert scores["B"] > scores["D"]


def test_bm25_ranks_phonics_query(tmp_path: Path):
    docs = [
        StandardDoc(
            standard_code="1.F.PA.4",
            text="Standard: 1.F.PA.4\nDomain: Phonological Awareness\nSyllables in spoken words",
            domain_primary="Phonological Awareness",
        ),
        StandardDoc(
            standard_code="1.T.T.1",
            text="Standard: 1.T.T.1\nDomain: Comprehension\nNarrative techniques and story details",
            domain_primary="Comprehension",
        ),
    ]
    hits = StandardsBm25Index(docs).search(
        "clap syllables in spoken words phonological awareness", limit=5
    )
    assert hits[0][0] == "1.F.PA.4"


def test_hybrid_rrf_with_mocked_dense(tmp_path: Path):
    qdrant = pytest.importorskip("qdrant_client")
    from qdrant_client.http import models as qm

    src = tmp_path / "normalize_standards"
    src.mkdir()
    docs_payload = [
        {
            "standard_code": "1.F.PA.4",
            "level": "standard",
            "grade": 1,
            "framework": "GA ELA",
            "label": "Syllables",
            "domain": {"primary": "Phonological Awareness", "secondary": []},
            "embed_text": "Standard: 1.F.PA.4 syllables spoken words phonological",
        },
        {
            "standard_code": "1.T.T.1",
            "level": "standard",
            "grade": 1,
            "framework": "GA ELA",
            "label": "Narrative",
            "domain": {"primary": "Comprehension", "secondary": []},
            "embed_text": "Standard: 1.T.T.1 narrative story comprehension",
        },
    ]
    for row in docs_payload:
        (src / f"{row['standard_code']}.json").write_text(
            json.dumps(row), encoding="utf-8"
        )

    dims = 8
    client = qdrant.QdrantClient(location=":memory:")
    client.create_collection(
        collection_name="test_stds",
        vectors_config=qm.VectorParams(size=dims, distance=qm.Distance.COSINE),
    )
    # Fake vectors: phonics-ish query closer to first doc.
    points = []
    for i, row in enumerate(docs_payload):
        vec = [0.1] * dims
        vec[0] = 1.0 if i == 0 else 0.1
        points.append(
            qm.PointStruct(
                id=i + 1,
                vector=vec,
                payload={
                    "standard_code": row["standard_code"],
                    "text": row["embed_text"],
                    "domain_primary": row["domain"]["primary"],
                    "label": row["label"],
                    "level": row["level"],
                    "grade": row["grade"],
                },
            )
        )
    client.upsert(collection_name="test_stds", points=points)

    def fake_embed(texts: list[str]) -> list[list[float]]:
        # Query vector biased toward phonics doc.
        v = [0.1] * dims
        v[0] = 0.95
        return [v for _ in texts]

    hits = hybrid_retrieve_standards(
        "students clap syllables in spoken words",
        src,
        top_k=2,
        arm_limit=2,
        collection="test_stds",
        dimensions=dims,
        embed_fn=fake_embed,
        qdrant_client=client,
    )
    assert len(hits) == 2
    assert hits[0].standard_code == "1.F.PA.4"
    assert hits[0].rrf_score > 0
    assert hits[0].dense_rank == 1


def test_rerank_orders_by_injected_scores():
    cands = [
        Candidate(standard_code="A", text="alpha", rrf_score=0.03),
        Candidate(standard_code="B", text="beta", rrf_score=0.02),
        Candidate(standard_code="C", text="gamma", rrf_score=0.01),
    ]

    def fake_scores(query: str, docs: list[str]) -> list[float]:
        assert query == "q"
        # Prefer B over A over C
        return [0.2, 0.9, 0.1]

    out = rerank_candidates("q", cands, top_n=2, score_fn=fake_scores)
    assert [c.standard_code for c in out] == ["B", "A"]
    assert out[0].rerank_score == 0.9


def test_retrieve_and_rerank_pipeline_mocked(tmp_path: Path):
    qdrant = pytest.importorskip("qdrant_client")
    from qdrant_client.http import models as qm

    src = tmp_path / "normalize_standards"
    src.mkdir()
    for code, text, domain in [
        ("1.F.PA.4", "syllables spoken phonological", "Phonological Awareness"),
        ("1.T.T.1", "narrative story comprehension", "Comprehension"),
        ("1.L.V.1", "vocabulary word meaning", "Vocabulary"),
    ]:
        (src / f"{code}.json").write_text(
            json.dumps(
                {
                    "standard_code": code,
                    "level": "standard",
                    "grade": 1,
                    "framework": "GA ELA",
                    "label": code,
                    "domain": {"primary": domain, "secondary": []},
                    "embed_text": text,
                }
            ),
            encoding="utf-8",
        )

    dims = 4
    client = qdrant.QdrantClient(location=":memory:")
    client.create_collection(
        "test_stds",
        vectors_config=qm.VectorParams(size=dims, distance=qm.Distance.COSINE),
    )
    client.upsert(
        "test_stds",
        points=[
            qm.PointStruct(
                id=i + 1,
                vector=[1.0 if i == 0 else 0.0, 0.1, 0.1, 0.1],
                payload={
                    "standard_code": code,
                    "text": text,
                    "domain_primary": domain,
                    "label": code,
                    "level": "standard",
                    "grade": 1,
                },
            )
            for i, (code, text, domain) in enumerate(
                [
                    ("1.F.PA.4", "syllables spoken phonological", "Phonological Awareness"),
                    ("1.T.T.1", "narrative story comprehension", "Comprehension"),
                    ("1.L.V.1", "vocabulary word meaning", "Vocabulary"),
                ]
            )
        ],
    )

    def fake_embed(texts: list[str]) -> list[list[float]]:
        return [[0.9, 0.1, 0.1, 0.1] for _ in texts]

    def fake_rerank(query: str, docs: list[str]) -> list[float]:
        # Boost any doc mentioning syllables.
        return [1.0 if "syllable" in d else 0.1 for d in docs]

    out = retrieve_and_rerank(
        "clap syllables",
        src,
        top_k=3,
        rerank_k=2,
        collection="test_stds",
        dimensions=dims,
        embed_fn=fake_embed,
        qdrant_client=client,
        rerank_score_fn=fake_rerank,
    )
    assert len(out) == 2
    assert out[0].standard_code == "1.F.PA.4"
    assert out[0].rerank_score == 1.0


def test_cli_retrieve_standards_wires():
    args = build_parser().parse_args(
        [
            "retrieve-standards",
            "--chunk-file",
            "output/chunks/by_lesson/G1M2U1L3.json",
            "--top-k",
            "30",
            "--rerank-k",
            "10",
            "--no-rerank",
        ]
    )
    assert args.func.__name__ == "cmd_retrieve_standards"
    assert args.top_k == 30
    assert args.rerank_k == 10
    assert args.no_rerank is True
