"""Unit tests for multi-arm merge aggregation and pool membership."""

from __future__ import annotations

from veramynd_parser.retrieve.rrf import (
    aggregate_multi_arm_rrf,
    reciprocal_rank_fusion,
    select_merge_pool,
)


def test_sum_matches_classic_reciprocal_rank_fusion():
    lists = [
        ["A", "B", "C"],
        ["B", "D", "A"],
        ["E", "B", "F"],
    ]
    weights = [1.0, 1.5, 0.8]
    classic = reciprocal_rank_fusion(lists, k=60, weights=weights)
    summed, _ = aggregate_multi_arm_rrf(
        lists, k=60, weights=weights, aggregation="sum"
    )
    assert classic == summed


def test_max_prefers_depth_over_breadth():
    depth = ["DEPTH"] + [f"x{i}" for i in range(20)]
    lists = [depth]
    for i in range(6):
        arm = [f"z{i}_{j}" for j in range(14)] + ["BREADTH"] + [f"z{i}_tail"]
        lists.append(arm)

    sum_ranked, _ = aggregate_multi_arm_rrf(lists, k=60, aggregation="sum")
    max_ranked, _ = aggregate_multi_arm_rrf(lists, k=60, aggregation="max")
    top1_ranked, _ = aggregate_multi_arm_rrf(
        lists, k=60, aggregation="top_k_sum", top_arms=1
    )

    sum_order = [code for code, _ in sum_ranked]
    max_order = [code for code, _ in max_ranked]
    top1_order = [code for code, _ in top1_ranked]

    assert sum_order.index("BREADTH") < sum_order.index("DEPTH")
    assert max_order.index("DEPTH") < max_order.index("BREADTH")
    assert top1_order.index("DEPTH") < top1_order.index("BREADTH")


def test_log_dampened_reduces_breadth_advantage():
    depth = ["DEPTH"] + [f"x{i}" for i in range(20)]
    lists = [depth]
    for i in range(8):
        arm = [f"z{i}_{j}" for j in range(14)] + ["BREADTH"] + [f"z{i}_tail"]
        lists.append(arm)

    sum_ranked, _ = aggregate_multi_arm_rrf(lists, k=60, aggregation="sum")
    damp_ranked, _ = aggregate_multi_arm_rrf(
        lists, k=60, aggregation="log_dampened", log_dampen_base=2.0
    )
    sum_scores = dict(sum_ranked)
    damp_scores = dict(damp_ranked)
    sum_gap = sum_scores["BREADTH"] - sum_scores["DEPTH"]
    damp_gap = damp_scores["BREADTH"] - damp_scores["DEPTH"]
    assert damp_gap < sum_gap
    breadth_ratio = damp_scores["BREADTH"] / sum_scores["BREADTH"]
    depth_ratio = damp_scores["DEPTH"] / sum_scores["DEPTH"]
    assert breadth_ratio < depth_ratio


def test_arm_provenance_includes_source_and_rank():
    lists = [["A", "B"], ["B", "C"]]
    ranked, arms = aggregate_multi_arm_rrf(
        lists,
        k=60,
        weights=[1.7, 0.8],
        sources=["objective", "domain_bridge"],
        aggregation="max",
    )
    assert ranked[0][0] in {"A", "B"}
    assert len(arms["B"]) == 2
    assert arms["B"][0]["source"] == "objective"
    assert arms["B"][0]["rank"] == 2
    assert arms["A"][0]["contribution"] == 1.7 / (60 + 1)


def test_union_pool_adds_sum_only_candidate_without_reordering_primary():
    """Primary-qualified docs keep order; sum-only docs are appended."""
    # Scores already computed: DEPTH/KEEP* win primary top-3; BROAD only wins sum.
    primary = [
        ("DEPTH", 0.050),
        ("KEEP1", 0.040),
        ("KEEP2", 0.030),
        ("KEEP3", 0.010),
        ("BROAD", 0.005),
    ]
    secondary_sum = [
        ("BROAD", 0.200),
        ("KEEP1", 0.090),
        ("DEPTH", 0.080),
        ("OTHER", 0.070),
        ("KEEP2", 0.020),
    ]

    single, _ = select_merge_pool(
        primary, merge_top_k=3, pool_membership_mode="single"
    )
    union, union_stats = select_merge_pool(
        primary,
        merge_top_k=3,
        pool_membership_mode="union",
        secondary_sum_ranked=secondary_sum,
    )

    single_ids = [c for c, _ in single]
    union_ids = [c for c, _ in union]
    assert single_ids == ["DEPTH", "KEEP1", "KEEP2"]
    assert "BROAD" not in single_ids
    assert union_ids[:3] == single_ids
    assert "BROAD" in union_ids
    assert union_stats["union_added_n"] >= 1
    # Primary scores unchanged for primary-qualified docs.
    assert dict(union)["DEPTH"] == 0.050
    assert dict(union)["KEEP1"] == 0.040
    assert dict(union)["KEEP2"] == 0.030
    assert dict(union)["BROAD"] == 0.005
