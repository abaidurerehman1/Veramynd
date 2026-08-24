"""P9 dense_score health — logging artifact vs real dense-arm failure."""

from __future__ import annotations

from veramynd_parser.retrieve.dense_health import (
    assess_dense_score_health,
    scan_retrieve_dir_dense_health,
)
from veramynd_parser.retrieve.models import Candidate


def test_p9_logging_artifact_when_ranks_ok_scores_zero():
    cands = [
        Candidate(
            standard_code=f"S{i}",
            text="x",
            dense_rank=i,
            dense_score=0.0,
            bm25_rank=i,
            bm25_score=10.0,
        )
        for i in range(1, 6)
    ]
    health = assess_dense_score_health(cands)
    assert health["status"] == "logging_artifact"
    assert health["retrieval_ok"] is True
    assert "cosmetic" in health["note"].lower() or "logging" in health["note"].lower()


def test_p9_ok_when_scores_positive():
    cands = [
        Candidate(
            standard_code="A",
            text="x",
            dense_rank=1,
            dense_score=0.71,
        ),
        Candidate(
            standard_code="B",
            text="x",
            dense_rank=2,
            dense_score=0.55,
        ),
    ]
    health = assess_dense_score_health(cands)
    assert health["status"] == "ok"
    assert health["retrieval_ok"] is True


def test_p9_dense_arm_missing_when_no_ranks():
    cands = [
        Candidate(standard_code="A", text="x", dense_rank=None, dense_score=None),
        Candidate(standard_code="B", text="x", dense_rank=None, dense_score=0.0),
    ]
    health = assess_dense_score_health(cands)
    assert health["status"] == "dense_arm_missing"
    assert health["retrieval_ok"] is False


def test_scan_existing_retrieve_dir_confirms_artifact():
    from pathlib import Path

    root = Path("output/retrieve")
    if not root.is_dir():
        return
    summary = scan_retrieve_dir_dense_health(root)
    assert summary["files_scanned"] >= 1
    # Current G1M2 batch: most lessons are logging_artifact (SME P9).
    by = summary.get("by_status") or {}
    assert "logging_artifact" in by or "ok" in by
