"""Gold-metric integrity: before-rerank numbers must never be faked."""

from __future__ import annotations

import json
from pathlib import Path

from veramynd_parser.retrieve.gold_metrics import report_leaf_recall


def _gold(path: Path, rows: list[dict]) -> Path:
    path.write_text(
        "\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8"
    )
    return path


def _retrieve(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_before_rerank_reported_unavailable_when_field_missing(tmp_path: Path):
    """Regression: artifacts without rrf_candidates fell back to the
    after-rerank list, so before_rerank_rrf duplicated after_rerank and faked
    a "rerank changed nothing" signal."""
    gold = _gold(
        tmp_path / "gold.jsonl",
        [{"resource_id": "L1", "standard_code": "A", "matched_status": "full"}],
    )
    _retrieve(
        tmp_path / "L1.json",
        {"candidates": [{"standard_code": "A"}, {"standard_code": "B"}]},
    )

    report = report_leaf_recall(gold, tmp_path, cutoffs=(10,))
    assert report["after_rerank"]["recall"]["@10"]["hits"] == 1
    assert report["before_rerank_rrf"] == {
        "available": False,
        "reason": report["before_rerank_rrf"]["reason"],
    }
    assert "rrf_candidates" in report["before_rerank_rrf"]["reason"]
    assert report["candidate_count_before_rerank"] is None


def test_before_rerank_computed_when_field_present(tmp_path: Path):
    gold = _gold(
        tmp_path / "gold.jsonl",
        [{"resource_id": "L1", "standard_code": "A", "matched_status": "partial"}],
    )
    _retrieve(
        tmp_path / "L1.json",
        {
            "candidates": [{"standard_code": "B"}, {"standard_code": "A"}],
            "rrf_candidates": [{"standard_code": "A"}, {"standard_code": "B"}],
        },
    )

    report = report_leaf_recall(gold, tmp_path, cutoffs=(10,))
    # Distinct funnels: gold is rank 1 before rerank, rank 2 after.
    assert report["before_rerank_rrf"]["mrr"] == 1.0
    assert report["after_rerank"]["mrr"] == 0.5
    assert report["candidate_count_before_rerank"] == 2
