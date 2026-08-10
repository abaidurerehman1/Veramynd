"""Unit tests for Step-7 shortlist sum-rank rescue slots."""

from __future__ import annotations

from veramynd_parser.retrieve.models import Candidate
from veramynd_parser.retrieve.pipeline import (
    apply_shortlist_rescue,
    build_judge_shortlist,
)


def test_shortlist_rescue_slots_n0_vs_n3():
    """Core keeps fused order; missing sum-strong injected; fused tail retained."""
    baseline = [
        Candidate(standard_code=f"F{i:03d}", text="x", final_rank=i + 1)
        for i in range(50)
    ]
    pool = {c.standard_code: c for c in baseline}
    pool["SUM_STRONG"] = Candidate(standard_code="SUM_STRONG", text="sum-strong")
    pool["WEAK_BOTH"] = Candidate(standard_code="WEAK_BOTH", text="weak")

    sum_ranks: dict[str, int] = {
        c.standard_code: 20 + i for i, c in enumerate(baseline)
    }
    # Top-5 fused candidate also strong by sum — stays core, never "rescued".
    sum_ranks["F004"] = 1
    sum_ranks["SUM_STRONG"] = 3
    sum_ranks["F047"] = 4
    sum_ranks["F048"] = 5
    sum_ranks["F049"] = 100
    sum_ranks["WEAK_BOTH"] = 150

    out0 = apply_shortlist_rescue(
        baseline, top_n=50, rescue_slots=0, pool=pool, sum_ranks=sum_ranks
    )
    assert [c.standard_code for c in out0] == [c.standard_code for c in baseline]
    assert all(c.rescued_via is None for c in out0)

    out3 = apply_shortlist_rescue(
        baseline, top_n=50, rescue_slots=3, pool=pool, sum_ranks=sum_ranks
    )
    assert len(out3) == 50
    assert [c.standard_code for c in out3[:47]] == [
        c.standard_code for c in baseline[:47]
    ]
    assert out3[4].standard_code == "F004"  # fused top-5 always core
    rescued = out3[47:]
    rescued_ids = [c.standard_code for c in rescued]
    # Inject true breadth miss first; pad remaining slots from fused tail.
    assert rescued_ids[0] == "SUM_STRONG"
    assert rescued[0].rescued_via == "sum"
    assert rescued[0].sum_rank == 3
    assert set(rescued_ids[1:]) <= {"F047", "F048", "F049"}
    assert "WEAK_BOTH" not in {c.standard_code for c in out3}
    # Mid fused hit near the cut is not silently dropped (was rank 48 baseline).
    assert "F047" in {c.standard_code for c in out3}


def test_build_judge_shortlist_rescue_zero_is_stable():
    """rescue_slots=0 freezes pure fused top_n (independent of default slots)."""
    reranked = [
        Candidate(standard_code=f"C{i}", text=str(i), rerank_score=1.0 - i / 100)
        for i in range(60)
    ]
    merged = [
        Candidate(
            standard_code=f"C{i}",
            text=str(i),
            rrf_score=1.0 - i / 100,
            arm_hits=[
                {
                    "query_index": 1,
                    "source": "skill",
                    "rank": i + 1,
                    "weight": 1.0,
                    "contribution": 1.0 / (60 + i + 1),
                }
            ],
        )
        for i in range(60)
    ]
    with_zero = build_judge_shortlist(
        reranked,
        merged,
        top_n=50,
        rrf_weight=0.5,
        preserve_rrf_top=0,
        parent_cap=50,
        rescue_slots=0,
    )
    again = build_judge_shortlist(
        reranked,
        merged,
        top_n=50,
        rrf_weight=0.5,
        preserve_rrf_top=0,
        parent_cap=50,
        rescue_slots=0,
    )
    assert [c.to_dict() for c in with_zero] == [c.to_dict() for c in again]
    assert all(c.rescued_via is None for c in with_zero)
