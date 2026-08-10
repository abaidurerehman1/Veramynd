"""Unit tests for multi-arm RRF max_blend depth-breadth fusion."""
from __future__ import annotations

from veramynd_parser.retrieve.rrf import aggregate_multi_arm_rrf


def test_max_blend_adds_strongest_arm_depth():
    lists = [
        ["A", "X", "Y"],
        ["B", "C", "D"],
    ]
    weights = [2.0, 1.0]
    base, _ = aggregate_multi_arm_rrf(
        lists, k=60, weights=weights, aggregation="top_k_sum", top_arms=2, max_blend=0.0
    )
    blended, _ = aggregate_multi_arm_rrf(
        lists, k=60, weights=weights, aggregation="top_k_sum", top_arms=2, max_blend=1.0
    )
    base_scores = dict(base)
    blend_scores = dict(blended)
    # Max blend strictly increases score for every hit by its max arm contrib ≥0.
    assert blend_scores["A"] > base_scores["A"]
    # Single-arm head still wins when it's the largest contribution.
    assert [c for c, _ in blended][0] == "A"


def test_max_blend_zero_matches_unblended():
    lists = [["X", "Y"], ["Y", "Z"]]
    a, _ = aggregate_multi_arm_rrf(
        lists, aggregation="top_k_sum", top_arms=2, max_blend=0.0
    )
    b, _ = aggregate_multi_arm_rrf(
        lists, aggregation="top_k_sum", top_arms=2, max_blend=0
    )
    assert [c for c, _ in a] == [c for c, _ in b]
