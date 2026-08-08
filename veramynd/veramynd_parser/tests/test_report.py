"""Tests for alignment CSV report export."""

from __future__ import annotations

import csv
import json
from pathlib import Path

from veramynd_parser.cli import build_parser
from veramynd_parser.report.exporter import export_alignment_report


def _judge_file(tmp_path: Path) -> Path:
    path = tmp_path / "G1M2U1L3.json"
    path.write_text(
        json.dumps(
            {
                "resource_id": "G1M2U1L3",
                "verdicts": [
                    {
                        "resource_id": "G1M2U1L3",
                        "standard_code": "1.T.T.1.a",
                        "matched_status": "partial",
                        "confidence": "high",
                        "grounded": True,
                        "evidence": "Who is the main character?",
                        "evidence_page": 70,
                        "rationale": "Some clauses met.",
                        "standard_raw_text": "Identify characters and setting.",
                        "judge_model": "gpt-4.1",
                        "prompt_version": "align_judge.v1.0",
                        "escalated": False,
                        "grounding_note": "ok",
                        "retrieval": {"rerank_score": 0.9, "rrf_score": 0.03},
                    },
                    {
                        "resource_id": "G1M2U1L3",
                        "standard_code": "1.T.RA.1",
                        "matched_status": "none",
                        "confidence": "high",
                        "grounded": True,
                        "evidence": "",
                        "evidence_page": None,
                        "rationale": "Not research.",
                        "standard_raw_text": "Conduct research.",
                        "judge_model": "gpt-4.1",
                        "prompt_version": "align_judge.v1.0",
                        "escalated": False,
                        "grounding_note": "no evidence required for none",
                        "retrieval": {},
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    return path


def test_export_includes_none_by_default(tmp_path: Path):
    src = _judge_file(tmp_path)
    csv_path = tmp_path / "out.csv"
    summary = export_alignment_report([src], out_csv=csv_path, include_none=True)
    assert summary["row_count"] == 2
    with csv_path.open(encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 2
    assert {r["matched_status"] for r in rows} == {"partial", "none"}


def test_export_can_drop_none(tmp_path: Path):
    src = _judge_file(tmp_path)
    csv_path = tmp_path / "aligned.csv"
    summary = export_alignment_report([src], out_csv=csv_path, include_none=False)
    assert summary["row_count"] == 1
    with csv_path.open(encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    assert rows[0]["standard_code"] == "1.T.T.1.a"


def test_cli_registers_report():
    parser = build_parser()
    args = parser.parse_args(
        ["report-alignments", "--judge-dir", "output/judge", "--out", "output/reports/x.csv"]
    )
    assert args.func.__name__ == "cmd_report_alignments"


def test_collect_skips_incomplete_sidecars(tmp_path: Path):
    from veramynd_parser.report.exporter import collect_judge_files

    good = _judge_file(tmp_path)
    bad = tmp_path / "G1M2U1L3.json.incomplete.json"
    bad.write_text(good.read_text(encoding="utf-8"), encoding="utf-8")
    files = collect_judge_files([tmp_path])
    assert files == [good]


def test_collect_skips_non_judge_json_in_dir(tmp_path: Path):
    """Regression: the exporter's own summary JSON written into the judge dir
    made every subsequent --judge-dir run hard-fail."""
    from veramynd_parser.report.exporter import collect_judge_files

    good = _judge_file(tmp_path)
    (tmp_path / "alignments.summary.json").write_text(
        json.dumps({"row_count": 2}), encoding="utf-8"
    )
    (tmp_path / "stray.json").write_text("[1, 2]", encoding="utf-8")
    files = collect_judge_files([tmp_path])
    assert files == [good]


def test_explicit_file_is_never_silently_dropped(tmp_path: Path):
    from veramynd_parser.report.exporter import collect_judge_files

    good = _judge_file(tmp_path)
    sidecar = tmp_path / "G1M2U1L3.json.incomplete.json"
    sidecar.write_text(good.read_text(encoding="utf-8"), encoding="utf-8")
    # Explicitly requested sidecars pass through instead of vanishing.
    assert collect_judge_files([sidecar]) == [sidecar]


def test_csv_formula_injection_guard(tmp_path: Path):
    path = tmp_path / "G1M2U1L9.json"
    path.write_text(
        json.dumps(
            {
                "resource_id": "G1M2U1L9",
                "verdicts": [
                    {
                        "resource_id": "G1M2U1L9",
                        "standard_code": "1.T.T.1.a",
                        "matched_status": "partial",
                        "confidence": "high",
                        "grounded": True,
                        "evidence": "=HYPERLINK(\"http://evil\",\"click\")",
                        "evidence_page": 1,
                        "rationale": "@cmd payload",
                        "standard_raw_text": "+SUM(1,2)",
                        "judge_model": "gpt-4.1",
                        "prompt_version": "align_judge.v1.0",
                        "escalated": False,
                        "grounding_note": "ok",
                        "retrieval": {},
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    out_csv = tmp_path / "alignments.csv"
    export_alignment_report([path], out_csv=out_csv, out_summary=None)
    with out_csv.open(newline="", encoding="utf-8") as f:
        row = list(csv.DictReader(f))[0]
    assert row["evidence"].startswith("'=")
    assert row["rationale"].startswith("'@")
    assert row["standard_raw_text"].startswith("'+")
