"""Stage-1 provenance-gate tests (trust_gate.py)."""

from __future__ import annotations

import json
from pathlib import Path

from veramynd_parser.trust_gate import (
    require_chunks_trusted,
    require_stage1_go,
    warn_untrusted_input_file,
)


def _stage1_tree(tmp_path: Path) -> Path:
    stage1 = tmp_path / "stage1"
    (stage1 / "lessons").mkdir(parents=True)
    return stage1


def test_stage1_gate_verdict_json_wins_over_legacy_text(tmp_path: Path):
    """The JSON verdict is the trust artifact — a GO-looking text report must
    not override a BLOCK verdict (this was the old text-parse fragility)."""
    stage1 = _stage1_tree(tmp_path)
    (stage1 / "verification_report.txt").write_text(
        "RESULT: 15 checks · 0 FAIL · 0 WARN → GO", encoding="utf-8"
    )
    (stage1 / "verification_verdict.json").write_text(
        json.dumps({"verdict": "BLOCK", "passed": False, "fail_count": 2}),
        encoding="utf-8",
    )
    assert require_stage1_go(stage1 / "lessons", allow_unverified=False) == 1


def test_stage1_gate_passes_on_go_verdict_json(tmp_path: Path):
    stage1 = _stage1_tree(tmp_path)
    (stage1 / "verification_verdict.json").write_text(
        json.dumps({"verdict": "GO", "passed": True, "fail_count": 0}),
        encoding="utf-8",
    )
    assert require_stage1_go(stage1 / "lessons", allow_unverified=False) is None


def test_stage1_gate_rejects_corrupt_verdict_json(tmp_path: Path):
    stage1 = _stage1_tree(tmp_path)
    (stage1 / "verification_verdict.json").write_text("{not json", encoding="utf-8")
    assert require_stage1_go(stage1 / "lessons", allow_unverified=False) == 1


def test_stage1_gate_legacy_text_fallback_still_works(tmp_path: Path):
    stage1 = _stage1_tree(tmp_path)
    (stage1 / "verification_report.txt").write_text(
        "RESULT: 15 checks · 0 FAIL · 1 WARN → GO", encoding="utf-8"
    )
    assert require_stage1_go(stage1 / "lessons", allow_unverified=False) is None
    (stage1 / "verification_report.txt").write_text(
        "RESULT: 15 checks · 2 FAIL · 0 WARN → BLOCK", encoding="utf-8"
    )
    assert require_stage1_go(stage1 / "lessons", allow_unverified=False) == 1


def test_stage1_gate_missing_everything_errors(tmp_path: Path):
    stage1 = _stage1_tree(tmp_path)
    assert require_stage1_go(stage1 / "lessons", allow_unverified=False) == 2
    assert require_stage1_go(stage1 / "lessons", allow_unverified=True) is None


def test_chunks_trusted_gate(tmp_path: Path):
    chunks = tmp_path / "chunks"
    chunks.mkdir()
    # No manifest / legacy manifest: warn but proceed.
    assert require_chunks_trusted(chunks, allow_unverified=False) is None
    (chunks / "chunk_manifest.json").write_text(json.dumps({"lessons": 3}), encoding="utf-8")
    assert require_chunks_trusted(chunks, allow_unverified=False) is None
    # Stamped unverified: hard error unless explicitly allowed.
    (chunks / "chunk_manifest.json").write_text(
        json.dumps({"stage1_verdict": "unverified"}), encoding="utf-8"
    )
    assert require_chunks_trusted(chunks, allow_unverified=False) == 1
    assert require_chunks_trusted(chunks, allow_unverified=True) is None
    (chunks / "chunk_manifest.json").write_text(
        json.dumps({"stage1_verdict": "GO"}), encoding="utf-8"
    )
    assert require_chunks_trusted(chunks, allow_unverified=False) is None


def test_untrusted_single_file_gates(tmp_path: Path):
    # Stage-1 lesson file inside a BLOCK export.
    stage1 = _stage1_tree(tmp_path)
    lesson_file = stage1 / "lessons" / "G1M2U1L1.json"
    lesson_file.write_text("{}", encoding="utf-8")
    (stage1 / "verification_verdict.json").write_text(
        json.dumps({"verdict": "BLOCK"}), encoding="utf-8"
    )
    assert warn_untrusted_input_file(str(lesson_file), "lesson") == 1
    (stage1 / "verification_verdict.json").write_text(
        json.dumps({"verdict": "GO"}), encoding="utf-8"
    )
    assert warn_untrusted_input_file(str(lesson_file), "lesson") is None

    # Chunk bundle whose manifest says unverified.
    chunks = tmp_path / "chunks"
    (chunks / "by_lesson").mkdir(parents=True)
    chunk_file = chunks / "by_lesson" / "G1M2U1L1.json"
    chunk_file.write_text("{}", encoding="utf-8")
    (chunks / "chunk_manifest.json").write_text(
        json.dumps({"stage1_verdict": "unverified"}), encoding="utf-8"
    )
    assert warn_untrusted_input_file(str(chunk_file), "chunk") == 1

    # Ad-hoc files with no provenance artifact are allowed.
    loose = tmp_path / "loose.json"
    loose.write_text("{}", encoding="utf-8")
    assert warn_untrusted_input_file(str(loose), "lesson") is None
    assert warn_untrusted_input_file(str(loose), "chunk") is None
    assert warn_untrusted_input_file(None, "lesson") is None


def test_untrusted_lesson_file_falls_back_to_legacy_text_report(tmp_path: Path):
    """Regression: unlike require_stage1_go, this gate had no legacy-report
    fallback — a lesson from an export made before verification_verdict.json
    existed, whose legacy verification_report.txt says BLOCK, passed with no
    warning at all (missing JSON verdict was treated as "ad-hoc, allow")."""
    stage1 = _stage1_tree(tmp_path)
    lesson_file = stage1 / "lessons" / "G1M2U1L1.json"
    lesson_file.write_text("{}", encoding="utf-8")
    (stage1 / "verification_report.txt").write_text(
        "RESULT: 15 checks · 2 FAIL · 0 WARN → BLOCK", encoding="utf-8"
    )
    assert warn_untrusted_input_file(str(lesson_file), "lesson") == 1

    (stage1 / "verification_report.txt").write_text(
        "RESULT: 15 checks · 0 FAIL · 0 WARN → GO", encoding="utf-8"
    )
    assert warn_untrusted_input_file(str(lesson_file), "lesson") is None
