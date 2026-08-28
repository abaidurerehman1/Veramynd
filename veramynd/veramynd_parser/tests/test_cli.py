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


# Stage-1 GO gate tests live in test_trust_gate.py (module extracted from cli.py).


def test_allow_unverified_flag_wires_on_downstream_commands():
    p = build_parser()
    for argv in (
        ["normalize-lessons", "output/stage1/lessons", "--allow-unverified"],
        [
            "judge-standards",
            "--retrieve-file", "r.json",
            "--lesson-file", "l.json",
            "--allow-unverified",
        ],
    ):
        assert p.parse_args(argv).allow_unverified is True
