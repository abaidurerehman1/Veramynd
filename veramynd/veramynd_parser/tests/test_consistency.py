"""Tests for P3 cross-lesson consistency pass."""

from __future__ import annotations

import json
from pathlib import Path

from veramynd_parser.judge.consistency import (
    apply_consistency_to_judge_dir,
    apply_cross_lesson_consistency,
    evidence_type_key,
)


_SHARED_EVIDENCE = (
    "Invite students to turn and talk with an elbow partner: "
    "What does the author tell us about Papa?"
)


def test_evidence_type_key_stable_for_same_quote():
    a = evidence_type_key(_SHARED_EVIDENCE)
    b = evidence_type_key(_SHARED_EVIDENCE.replace("Papa?", "Papa?"))
    assert a is not None
    assert a == b


def test_evidence_type_key_skips_empty_none_rows():
    assert evidence_type_key("") is None
    assert evidence_type_key("short") is None


def test_p3_flags_and_reconciles_same_evidence_type_different_labels():
    rows = [
        {
            "resource_id": "G1M2U1L8",
            "standard_code": "1.P.CP.1.d",
            "matched_status": "full",
            "evidence": _SHARED_EVIDENCE,
            "confidence": "high",
            "needs_review": False,
            "review_reason": "",
            "rationale": "OR-list → Full",
        },
        {
            "resource_id": "G1M2U1L9",
            "standard_code": "1.P.CP.1.d",
            "matched_status": "full",
            "evidence": _SHARED_EVIDENCE,
            "confidence": "high",
            "needs_review": False,
            "review_reason": "",
            "rationale": "OR-list → Full",
        },
        {
            "resource_id": "G1M2U1L10",
            "standard_code": "1.P.CP.1.d",
            "matched_status": "partial",
            "evidence": _SHARED_EVIDENCE,
            "confidence": "high",
            "needs_review": False,
            "review_reason": "",
            "rationale": "Waffle Partial",
        },
    ]
    out, summary = apply_cross_lesson_consistency(rows, reconcile=True)
    assert summary["conflict_groups"] == 1
    assert summary["rows_flagged"] == 3
    assert summary["rows_reconciled"] == 1
    by_id = {r["resource_id"]: r for r in out}
    assert by_id["G1M2U1L10"]["matched_status"] == "full"
    assert by_id["G1M2U1L10"]["needs_review"] is True
    assert "cross-lesson inconsistency" in by_id["G1M2U1L10"]["review_reason"]
    assert "P3 CONSISTENCY" in by_id["G1M2U1L10"]["rationale"]
    assert by_id["G1M2U1L8"]["needs_review"] is True


def test_p3_does_not_merge_different_evidence_types():
    rows = [
        {
            "resource_id": "L1",
            "standard_code": "1.L.V.1.b",
            "matched_status": "partial",
            "evidence": (
                "Students complete the frame: I noticed that the sun __________. "
                "One thing I wonder about the moon is ____________."
            ),
            "confidence": "high",
            "needs_review": False,
            "review_reason": "",
            "rationale": "two settings",
        },
        {
            "resource_id": "L3",
            "standard_code": "1.L.V.1.b",
            "matched_status": "none",
            "evidence": (
                "Teacher reads the lyrics aloud and students echo the word "
                "orbit after the teacher defines it once."
            ),
            "confidence": "high",
            "needs_review": False,
            "review_reason": "",
            "rationale": "echo only",
        },
    ]
    out, summary = apply_cross_lesson_consistency(rows, reconcile=True)
    assert summary["conflict_groups"] == 0
    assert out[0]["matched_status"] == "partial"
    assert out[1]["matched_status"] == "none"
    assert out[0]["needs_review"] is False


def test_p3_flag_only_without_reconcile():
    rows = [
        {
            "resource_id": "A",
            "standard_code": "1.P.CP.1.d",
            "matched_status": "full",
            "evidence": _SHARED_EVIDENCE,
            "confidence": "high",
            "needs_review": False,
            "review_reason": "",
            "rationale": "a",
        },
        {
            "resource_id": "B",
            "standard_code": "1.P.CP.1.d",
            "matched_status": "partial",
            "evidence": _SHARED_EVIDENCE,
            "confidence": "high",
            "needs_review": False,
            "review_reason": "",
            "rationale": "b",
        },
    ]
    out, summary = apply_cross_lesson_consistency(rows, reconcile=False)
    assert summary["conflict_groups"] == 1
    assert summary["rows_reconciled"] == 0
    assert out[0]["matched_status"] == "full"
    assert out[1]["matched_status"] == "partial"
    assert out[0]["needs_review"] is True
    assert out[1]["needs_review"] is True


def test_apply_consistency_to_judge_dir(tmp_path: Path):
    for rid, status in (
        ("G1M2U1L1", "full"),
        ("G1M2U1L2", "full"),
        ("G1M2U1L3", "partial"),
    ):
        payload = {
            "resource_id": rid,
            "verdicts": [
                {
                    "resource_id": rid,
                    "standard_code": "1.P.CP.1.d",
                    "matched_status": status,
                    "evidence": _SHARED_EVIDENCE,
                    "confidence": "high",
                    "needs_review": False,
                    "review_reason": "",
                    "rationale": "x",
                }
            ],
        }
        (tmp_path / f"{rid}.json").write_text(
            json.dumps(payload, indent=2) + "\n", encoding="utf-8"
        )

    summary = apply_consistency_to_judge_dir(tmp_path, reconcile=True, rewrite=True)
    assert summary["conflict_groups"] == 1
    assert summary["rows_reconciled"] == 1

    l3 = json.loads((tmp_path / "G1M2U1L3.json").read_text(encoding="utf-8"))
    assert l3["verdicts"][0]["matched_status"] == "full"
    assert l3["verdicts"][0]["needs_review"] is True
