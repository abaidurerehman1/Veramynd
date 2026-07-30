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
