"""Stage-rank diagnostics remain independent from retrieval scoring."""

from __future__ import annotations

from veramynd_parser.retrieve.diagnostics import (
    build_diagnostics_payload,
    gold_rank_movements,
)
from veramynd_parser.retrieve.models import Candidate


def test_diagnostics_emits_dense_bm25_rrf_reranker_final_ranks():
    per_query = [
        {
            "query_id": "lesson#objective#1",
            "source": "objective",
            "dense_codes": ["A", "B", "C"],
            "bm25_codes": ["B", "C", "A"],
            "hybrid_codes": ["B", "A", "C"],
        },
        {
            "query_id": "lesson#skill_1#2",
            "source": "skill_1",
            "dense_codes": ["C", "A", "B"],
            "bm25_codes": ["C", "B", "A"],
            "hybrid_codes": ["C", "B", "A"],
        },
    ]
    merged = [
        Candidate("C", "c", rrf_rank=1),
        Candidate("B", "b", rrf_rank=2),
        Candidate("A", "a", rrf_rank=3),
    ]
    reranked = [
        Candidate("A", "a", rerank_rank=1),
        Candidate("C", "c", rerank_rank=2),
        Candidate("B", "b", rerank_rank=3),
    ]
    final = [
        Candidate("A", "a", final_rank=1),
        Candidate("B", "b", final_rank=2),
    ]

    payload = build_diagnostics_payload(
        resource_id="lesson",
        queries=[],
        per_query=per_query,
        merged=merged,
        reranked=reranked,
        shortlist=final,
        gold_codes=["C"],
    )
    rows = {row["standard_code"]: row for row in payload["candidate_stage_ranks"]}
    assert rows["A"]["dense_rank"] == 1
    assert rows["B"]["bm25_rank"] == 1
    assert rows["C"]["rrf_rank"] == 1
    assert rows["A"]["reranker_rank"] == 1
    assert rows["B"]["final_rank"] == 2

    movement = payload["gold_rank_movements"][0]
    assert movement["standard_code"] == "C"
    assert movement["rrf_rank"] == 1
    assert movement["reranker_rank"] == 2
    assert movement["final_rank"] is None
    assert movement["lost_at"] == "shortlist"


def test_lost_at_never_blames_a_stage_for_shortlisted_candidates():
    """Regression: the classifier stopped at the first stage a code was absent
    from, so rescue-slot entries (skip rerank) and grade-exhaustive CE
    candidates (skip merge) were labeled "lost" while sitting in the final
    shortlist of the same row."""
    per_query = [
        {
            "query_id": "q1",
            "source": "objective",
            "dense_codes": ["RESCUED", "LOST_CE"],
            "bm25_codes": ["RESCUED"],
            "hybrid_codes": ["RESCUED"],
        }
    ]
    rows = gold_rank_movements(
        gold_codes=["RESCUED", "CE_ONLY", "LOST_CE"],
        per_query=per_query,
        # RESCUED made merge but missed the CE top-k; entered shortlist via
        # rescue. CE_ONLY and LOST_CE never made the merge; both were reranked,
        # only CE_ONLY survived to the shortlist.
        merged_codes=["RESCUED"],
        reranked_codes=["CE_ONLY", "LOST_CE"],
        shortlist_codes=["CE_ONLY", "RESCUED"],
    )
    by_code = {r["standard_code"]: r for r in rows}
    assert by_code["RESCUED"]["lost_at"] is None
    assert by_code["CE_ONLY"]["lost_at"] is None
    # Lost after surviving rerank — blame the shortlist, not merge_rrf.
    assert by_code["LOST_CE"]["lost_at"] == "shortlist"
