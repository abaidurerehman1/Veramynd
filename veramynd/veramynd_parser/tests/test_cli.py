"""CLI argument-wiring and export-gate tests.

These exercise the real argparse parser end-to-end (build_parser().parse_args)
plus the enforcement logic in cmd_export, without needing the real reference PDF
for the pure argument-wiring tests. The export-gate tests do use the reference
PDF (guide_path fixture, PyMuPDF engine — no Docling needed) since they exercise
the real parse/verify/write pipeline.
"""

from __future__ import annotations

import json
from pathlib import Path

from veramynd_parser.cli import (
    _config,
    _require_chunks_trusted,
    _require_stage1_go,
    _warn_untrusted_input_file,
    build_parser,
    cmd_export,
)


def test_cross_engine_flag_defaults_off():
    args = build_parser().parse_args(["verify", "guide.pdf"])
    assert args.cross_engine is False
    assert _config(args).cross_engine_structural_check is False


def test_cross_engine_flag_wires_into_config_for_verify():
    """Regression target: cross-engine verification (V15) exists in verify() but
    was reported as unreachable from the CLI. --cross-engine must actually flip
    Config.cross_engine_structural_check, which is what verify() reads."""
    args = build_parser().parse_args(["verify", "guide.pdf", "--cross-engine"])
    assert args.cross_engine is True
    assert _config(args).cross_engine_structural_check is True


def test_cross_engine_flag_wires_into_config_for_export():
    args = build_parser().parse_args(["export", "guide.pdf", "--cross-engine"])
    assert _config(args).cross_engine_structural_check is True


def test_cross_engine_flag_wires_into_config_for_guide():
    args = build_parser().parse_args(["guide", "guide.pdf", "--cross-engine"])
    assert _config(args).cross_engine_structural_check is True


def test_allow_block_flag_defaults_off():
    args = build_parser().parse_args(["export", "guide.pdf"])
    assert args.allow_block is False


def test_allow_block_flag_can_be_set():
    args = build_parser().parse_args(["export", "guide.pdf", "--allow-block"])
    assert args.allow_block is True


class _Args:
    """Minimal argparse.Namespace-alike for calling cmd_export directly without
    going through argv parsing."""

    def __init__(self, **kwargs):
        self.engine = "pymupdf"
        self.ocr = "auto"
        self.pdf_pages = False
        self.cross_engine = False
        self.standards = None
        self.allow_block = False
        self.__dict__.update(kwargs)


def _docling_or_skip():
    import importlib.util

    import pytest

    if importlib.util.find_spec("docling") is None:
        pytest.skip("docling not installed (production Stage 1 engine)")
    return "docling"


def test_export_withholds_trusted_output_on_block(guide_path, tmp_path: Path):
    out = tmp_path / "out"
    args = _Args(path=str(guide_path), out=str(out), expect=39)  # wrong count -> BLOCK
    code = cmd_export(args)
    assert code != 0
    assert (out / "verification_report.txt").is_file()
    verdict = json.loads(
        (out / "verification_verdict.json").read_text(encoding="utf-8")
    )
    assert verdict["verdict"] == "BLOCK"
    assert verdict["fail_count"] >= 1
    assert not (out / "teacher_guide.json").exists()
    assert not (out / "lessons").exists()
    assert not (out / "lessons_index.tsv").exists()


def test_export_writes_output_on_go(guide_path, tmp_path: Path):
    out = tmp_path / "out"
    args = _Args(
        path=str(guide_path),
        out=str(out),
        expect=40,
        engine=_docling_or_skip(),
    )
    code = cmd_export(args)
    assert code == 0
    assert (out / "teacher_guide.json").is_file()
    assert (out / "lessons").is_dir()
    assert list((out / "lessons").glob("*.json"))
    assert (out / "verification_report.txt").is_file()
    assert "GO" in (out / "verification_report.txt").read_text(encoding="utf-8")


def test_export_allow_block_writes_output_anyway(guide_path, tmp_path: Path):
    out = tmp_path / "out"
    args = _Args(path=str(guide_path), out=str(out), expect=39, allow_block=True)
    code = cmd_export(args)
    assert code != 0  # exit code still reflects BLOCK
    assert (out / "teacher_guide.json").is_file()  # but output was written anyway
    assert list((out / "lessons").glob("*.json"))


def test_export_standards_failure_does_not_leave_fresh_go_report(
    guide_path, tmp_path: Path
):
    """GO report must not be written before standards parse succeeds — otherwise a
    failed standards path leaves a trusted-looking report beside a stale lessons/."""
    out = tmp_path / "out"
    out.mkdir()
    (out / "verification_report.txt").write_text("OLD REPORT\n", encoding="utf-8")
    bad = tmp_path / "bad.xlsx"
    bad.write_bytes(b"not-an-xlsx")
    args = _Args(
        path=str(guide_path),
        out=str(out),
        expect=40,
        engine=_docling_or_skip(),
        standards=str(bad),
    )
    code = cmd_export(args)
    assert code != 0
    report = (out / "verification_report.txt").read_text(encoding="utf-8")
    # Must remain the seeded prior report — not a fresh GO from this failed run.
    assert report == "OLD REPORT\n"
    assert not (out / "verification_verdict.json").exists()
    assert not (out / "teacher_guide.json").exists()


# ---- Stage-1 GO gate (machine-readable verdict) ----------------------------


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
    assert _require_stage1_go(stage1 / "lessons", allow_unverified=False) == 1


def test_stage1_gate_passes_on_go_verdict_json(tmp_path: Path):
    stage1 = _stage1_tree(tmp_path)
    (stage1 / "verification_verdict.json").write_text(
        json.dumps({"verdict": "GO", "passed": True, "fail_count": 0}),
        encoding="utf-8",
    )
    assert _require_stage1_go(stage1 / "lessons", allow_unverified=False) is None


def test_stage1_gate_rejects_corrupt_verdict_json(tmp_path: Path):
    stage1 = _stage1_tree(tmp_path)
    (stage1 / "verification_verdict.json").write_text("{not json", encoding="utf-8")
    assert _require_stage1_go(stage1 / "lessons", allow_unverified=False) == 1


def test_stage1_gate_legacy_text_fallback_still_works(tmp_path: Path):
    stage1 = _stage1_tree(tmp_path)
    (stage1 / "verification_report.txt").write_text(
        "RESULT: 15 checks · 0 FAIL · 1 WARN → GO", encoding="utf-8"
    )
    assert _require_stage1_go(stage1 / "lessons", allow_unverified=False) is None
    (stage1 / "verification_report.txt").write_text(
        "RESULT: 15 checks · 2 FAIL · 0 WARN → BLOCK", encoding="utf-8"
    )
    assert _require_stage1_go(stage1 / "lessons", allow_unverified=False) == 1


def test_stage1_gate_missing_everything_errors(tmp_path: Path):
    stage1 = _stage1_tree(tmp_path)
    assert _require_stage1_go(stage1 / "lessons", allow_unverified=False) == 2
    assert _require_stage1_go(stage1 / "lessons", allow_unverified=True) is None


def test_chunks_trusted_gate(tmp_path: Path):
    chunks = tmp_path / "chunks"
    chunks.mkdir()
    # No manifest / legacy manifest: warn but proceed.
    assert _require_chunks_trusted(chunks, allow_unverified=False) is None
    (chunks / "chunk_manifest.json").write_text(json.dumps({"lessons": 3}), encoding="utf-8")
    assert _require_chunks_trusted(chunks, allow_unverified=False) is None
    # Stamped unverified: hard error unless explicitly allowed.
    (chunks / "chunk_manifest.json").write_text(
        json.dumps({"stage1_verdict": "unverified"}), encoding="utf-8"
    )
    assert _require_chunks_trusted(chunks, allow_unverified=False) == 1
    assert _require_chunks_trusted(chunks, allow_unverified=True) is None
    (chunks / "chunk_manifest.json").write_text(
        json.dumps({"stage1_verdict": "GO"}), encoding="utf-8"
    )
    assert _require_chunks_trusted(chunks, allow_unverified=False) is None


def test_untrusted_single_file_gates(tmp_path: Path):
    # Stage-1 lesson file inside a BLOCK export.
    stage1 = _stage1_tree(tmp_path)
    lesson_file = stage1 / "lessons" / "G1M2U1L1.json"
    lesson_file.write_text("{}", encoding="utf-8")
    (stage1 / "verification_verdict.json").write_text(
        json.dumps({"verdict": "BLOCK"}), encoding="utf-8"
    )
    assert _warn_untrusted_input_file(str(lesson_file), "lesson") == 1
    (stage1 / "verification_verdict.json").write_text(
        json.dumps({"verdict": "GO"}), encoding="utf-8"
    )
    assert _warn_untrusted_input_file(str(lesson_file), "lesson") is None

    # Chunk bundle whose manifest says unverified.
    chunks = tmp_path / "chunks"
    (chunks / "by_lesson").mkdir(parents=True)
    chunk_file = chunks / "by_lesson" / "G1M2U1L1.json"
    chunk_file.write_text("{}", encoding="utf-8")
    (chunks / "chunk_manifest.json").write_text(
        json.dumps({"stage1_verdict": "unverified"}), encoding="utf-8"
    )
    assert _warn_untrusted_input_file(str(chunk_file), "chunk") == 1

    # Ad-hoc files with no provenance artifact are allowed.
    loose = tmp_path / "loose.json"
    loose.write_text("{}", encoding="utf-8")
    assert _warn_untrusted_input_file(str(loose), "lesson") is None
    assert _warn_untrusted_input_file(str(loose), "chunk") is None
    assert _warn_untrusted_input_file(None, "lesson") is None


def test_untrusted_lesson_file_falls_back_to_legacy_text_report(tmp_path: Path):
    """Regression: unlike _require_stage1_go, this gate had no legacy-report
    fallback — a lesson from an export made before verification_verdict.json
    existed, whose legacy verification_report.txt says BLOCK, passed with no
    warning at all (missing JSON verdict was treated as "ad-hoc, allow")."""
    stage1 = _stage1_tree(tmp_path)
    lesson_file = stage1 / "lessons" / "G1M2U1L1.json"
    lesson_file.write_text("{}", encoding="utf-8")
    (stage1 / "verification_report.txt").write_text(
        "RESULT: 15 checks · 2 FAIL · 0 WARN → BLOCK", encoding="utf-8"
    )
    assert _warn_untrusted_input_file(str(lesson_file), "lesson") == 1

    (stage1 / "verification_report.txt").write_text(
        "RESULT: 15 checks · 0 FAIL · 0 WARN → GO", encoding="utf-8"
    )
    assert _warn_untrusted_input_file(str(lesson_file), "lesson") is None


def test_allow_unverified_flag_wires_on_downstream_commands():
    p = build_parser()
    for argv in (
        ["chunk-lessons", "output/stage1/lessons", "--allow-unverified"],
        ["embed-chunks", "output/chunks", "--allow-unverified"],
        ["retrieve-standards", "--query", "q", "--allow-unverified"],
        [
            "judge-standards",
            "--retrieve-file", "r.json",
            "--lesson-file", "l.json",
            "--allow-unverified",
        ],
    ):
        assert p.parse_args(argv).allow_unverified is True
