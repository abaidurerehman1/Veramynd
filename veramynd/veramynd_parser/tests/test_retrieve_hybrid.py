"""Tests for hybrid dense+BM25+RRF and cross-encoder rerank."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from veramynd_parser.cli import build_parser
from veramynd_parser.retrieve.bm25 import StandardsBm25Index, tokenize
from veramynd_parser.retrieve.models import Candidate, StandardDoc
from veramynd_parser.retrieve.pipeline import (
    build_judge_shortlist,
    build_local_rerank_pool,
    hybrid_retrieve_standards,
    multi_query_hybrid_retrieve,
    retrieve_and_rerank,
)
from veramynd_parser.retrieve.rerank import (
    format_rerank_query,
    rerank_candidates,
)
from veramynd_parser.retrieve.rrf import reciprocal_rank_fusion


def test_tokenize_keeps_dotted_codes():
    toks = tokenize("Standard 1.F.PA.4 syllables in spoken words")
    assert "1.f.pa.4" in toks
    assert "syllables" in toks


def test_judge_shortlist_fuses_rerank_and_first_stage_rrf():
    reranked = [
        Candidate(standard_code="A", text="a", rerank_score=0.9),
        Candidate(standard_code="B", text="b", rerank_score=0.8),
        Candidate(standard_code="C", text="c", rerank_score=0.7),
    ]
    merged = [
        Candidate(standard_code="C", text="c", rrf_score=0.3),
        Candidate(standard_code="D", text="d", rrf_score=0.2),
        Candidate(standard_code="A", text="a", rrf_score=0.1),
    ]
    out = build_judge_shortlist(reranked, merged, top_n=3, rrf_weight=0.5)
    assert len(out) == 3
    assert len({c.standard_code for c in out}) == 3
    assert "C" in {c.standard_code for c in out}


def test_judge_shortlist_defers_consecutive_siblings_without_dropping_budget():
    reranked = [
        Candidate(
            standard_code=f"1.X.1.{suffix}",
            text=suffix,
            parent_code="1.X.1",
            rerank_score=1.0 - i / 10,
        )
        for i, suffix in enumerate(("a", "b", "c", "d", "e"))
    ] + [
        Candidate(
            standard_code=f"1.Y.{i}.a",
            text=str(i),
            parent_code=f"1.Y.{i}",
            rerank_score=0.4 - i / 100,
        )
        for i in range(1, 6)
    ]
    out = build_judge_shortlist(
        reranked,
        reranked,
        top_n=6,
        rrf_weight=0.0,
        preserve_rrf_top=0,
        parent_cap=3,
    )
    assert len(out) == 6
    families = [c.parent_code for c in out]
    max_streak = 1
    streak = 1
    for prior, current in zip(families, families[1:]):
        streak = streak + 1 if current == prior else 1
        max_streak = max(max_streak, streak)
    assert max_streak <= 3
    assert [c.final_rank for c in out] == list(range(1, 7))


def test_local_rerank_pool_is_grade_exhaustive_below_ceiling(tmp_path: Path):
    src = tmp_path / "normalize_standards"
    src.mkdir()
    for code, grade in (("1.A.1.a", 1), ("1.B.1.a", 1), ("2.A.1.a", 2)):
        (src / f"{code}.json").write_text(
            json.dumps(
                {
                    "standard_code": code,
                    "level": "substandard",
                    "grade": grade,
                    "framework": "test",
                    "parent_code": code.rsplit(".", 1)[0],
                    "domain": {"primary": "Comprehension", "secondary": []},
                    "embed_text": f"Students understand {code}.",
                }
            ),
            encoding="utf-8",
        )
    merged = [Candidate(standard_code="1.A.1.a", text="a")]
    pool, mode = build_local_rerank_pool(
        src, merged, grade=1, exhaustive_ceiling=10
    )
    assert mode == "grade_exhaustive"
    assert {c.standard_code for c in pool} == {"1.A.1.a", "1.B.1.a"}
    assert next(c for c in pool if c.standard_code == "1.B.1.a").parent_code == "1.B.1"


def test_filter_alignable_leaves_drops_parents():
    from veramynd_parser.retrieve.leaves import filter_alignable_leaves

    docs = [
        StandardDoc(
            standard_code="1.T.RA.1",
            text="parent folder",
            level="standard",
            metadata={},
        ),
        StandardDoc(
            standard_code="1.T.RA.1.a",
            text="ask questions leaf",
            level="substandard",
            metadata={"parent_code": "1.T.RA.1"},
        ),
        StandardDoc(
            standard_code="1.T.RA.1.b",
            text="research leaf",
            level="substandard",
            metadata={"parent_code": "1.T.RA.1"},
        ),
        StandardDoc(
            standard_code="1.T",
            text="domain",
            level="domain",
            metadata={},
        ),
    ]
    leaves = filter_alignable_leaves(docs)
    assert {d.standard_code for d in leaves} == {"1.T.RA.1.a", "1.T.RA.1.b"}


def test_multi_query_rrf_merge_prefers_codes_seen_across_queries(tmp_path: Path):
    """Two instructional queries; code strong in both should rank above one-hit noise."""
    qdrant = pytest.importorskip("qdrant_client")
    from qdrant_client.http import models as qm

    src = tmp_path / "normalize_standards"
    src.mkdir()
    rows = [
        {
            "standard_code": "1.T.RA.1.a",
            "level": "substandard",
            "parent_code": "1.T.RA.1",
            "grade": 1,
            "framework": "GA ELA",
            "label": "Ask",
            "domain": {"primary": "Comprehension", "secondary": []},
            "embed_text": "ask questions topics interest research",
        },
        {
            "standard_code": "1.F.PA.4.d",
            "level": "substandard",
            "parent_code": "1.F.PA.4",
            "grade": 1,
            "framework": "GA ELA",
            "label": "Syllables",
            "domain": {"primary": "Foundations", "secondary": []},
            "embed_text": "syllables spoken words phonological",
        },
        {
            "standard_code": "1.L.V.1.a",
            "level": "substandard",
            "parent_code": "1.L.V.1",
            "grade": 1,
            "framework": "GA ELA",
            "label": "Vocab",
            "domain": {"primary": "Language", "secondary": []},
            "embed_text": "vocabulary words phrases grade-level texts",
        },
    ]
    for row in rows:
        (src / f"{row['standard_code']}.json").write_text(
            json.dumps(row), encoding="utf-8"
        )

    dims = 6
    client = qdrant.QdrantClient(location=":memory:")
    client.create_collection(
        "test_multi",
        vectors_config=qm.VectorParams(size=dims, distance=qm.Distance.COSINE),
    )
    # Vectors: ask≈[1,0,...], syllables≈[0,1,...], vocab≈[0,0,1,...]
    vecs = {
        "1.T.RA.1.a": [1.0, 0.0, 0.0, 0.0, 0.0, 0.0],
        "1.F.PA.4.d": [0.0, 1.0, 0.0, 0.0, 0.0, 0.0],
        "1.L.V.1.a": [0.0, 0.0, 1.0, 0.0, 0.0, 0.0],
    }
    for i, row in enumerate(rows):
        client.upsert(
            "test_multi",
            points=[
                qm.PointStruct(
                    id=i + 1,
                    vector=vecs[row["standard_code"]],
                    payload={
                        "standard_code": row["standard_code"],
                        "text": row["embed_text"],
                        "domain_primary": row["domain"]["primary"],
                        "label": row["label"],
                        "level": row["level"],
                        "grade": 1,
                    },
                )
            ],
        )

    def fake_embed(texts: list[str]) -> list[list[float]]:
        out = []
        for t in texts:
            tl = t.lower()
            if "question" in tl or "research" in tl:
                out.append([0.95, 0.05, 0.0, 0.0, 0.0, 0.0])
            elif "syllable" in tl:
                out.append([0.05, 0.95, 0.0, 0.0, 0.0, 0.0])
            else:
                out.append([0.1, 0.1, 0.8, 0.0, 0.0, 0.0])
        return out

    merged, _diag = multi_query_hybrid_retrieve(
        [
            "students ask questions about topics for research",
            "students ask and generate research questions",
        ],
        src,
        per_query_top_k=3,
        merge_top_k=3,
        arm_limit=5,
        collection="test_multi",
        dimensions=dims,
        embed_fn=fake_embed,
        qdrant_client=client,
    )
    assert merged[0].standard_code == "1.T.RA.1.a"
    assert all(c.level == "substandard" for c in merged)


def test_hybrid_excludes_parent_even_if_dense_ranks_it_first(tmp_path: Path):
    qdrant = pytest.importorskip("qdrant_client")
    from qdrant_client.http import models as qm

    src = tmp_path / "normalize_standards"
    src.mkdir()
    rows = [
        {
            "standard_code": "1.T.RA.1",
            "level": "standard",
            "grade": 1,
            "framework": "GA ELA",
            "label": "Research",
            "parent_code": "1.T.RA",
            "domain": {"primary": "Comprehension", "secondary": []},
            "embed_text": "ask questions research topics of interest",
        },
        {
            "standard_code": "1.T.RA.1.a",
            "level": "substandard",
            "grade": 1,
            "framework": "GA ELA",
            "label": "Ask",
            "parent_code": "1.T.RA.1",
            "domain": {"primary": "Comprehension", "secondary": []},
            "embed_text": "Ask questions about topics of interest for research",
        },
        {
            "standard_code": "1.F.PA.4.d",
            "level": "substandard",
            "grade": 1,
            "framework": "GA ELA",
            "label": "Syllables",
            "parent_code": "1.F.PA.4",
            "domain": {"primary": "Foundations", "secondary": []},
            "embed_text": "Add delete substitute syllables in spoken words",
        },
    ]
    for row in rows:
        (src / f"{row['standard_code']}.json").write_text(
            json.dumps(row), encoding="utf-8"
        )

    dims = 8
    client = qdrant.QdrantClient(location=":memory:")
    client.create_collection(
        collection_name="test_stds_leaf",
        vectors_config=qm.VectorParams(size=dims, distance=qm.Distance.COSINE),
    )
    # Parent vector closest to query — leaf-only must still drop it.
    for i, row in enumerate(rows):
        vec = [0.05] * dims
        vec[0] = 1.0 if i == 0 else (0.8 if i == 1 else 0.1)
        client.upsert(
            collection_name="test_stds_leaf",
            points=[
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
            ],
        )

    def fake_embed(texts: list[str]) -> list[list[float]]:
        v = [0.05] * dims
        v[0] = 0.99
        return [v for _ in texts]

    hits = hybrid_retrieve_standards(
        "ask questions about topics of interest for research",
        src,
        top_k=5,
        arm_limit=5,
        collection="test_stds_leaf",
        dimensions=dims,
        embed_fn=fake_embed,
        qdrant_client=client,
    )
    codes = [c.standard_code for c in hits]
    assert "1.T.RA.1" not in codes
    assert "1.T.RA.1.a" in codes
    assert all(c.level == "substandard" for c in hits)


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
        assert query == format_rerank_query("q")
        assert docs == ["alpha", "beta", "gamma"]
        # Prefer B over A over C
        return [0.2, 0.9, 0.1]

    out = rerank_candidates("q", cands, top_n=2, score_fn=fake_scores)
    assert [c.standard_code for c in out] == ["B", "A"]
    assert out[0].rerank_score == 0.9
    assert out[0].rerank_rank == 1
    assert out[0].blended_score is not None


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
