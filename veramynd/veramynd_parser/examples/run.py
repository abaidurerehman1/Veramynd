#!/usr/bin/env python3
"""End-to-end example: parse the guide and standards, verify, print a summary.

    python examples/run.py
"""

from __future__ import annotations

import sys
from pathlib import Path

# allow running without `pip install` by putting the package root on the path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from veramynd_parser import Config, parse_standards, parse_teacher_guide, verify  # noqa: E402
from veramynd_parser.pdf.document import PdfDocument  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]
SAMPLES = REPO_ROOT / "data" / "samples"
GUIDE = SAMPLES / "ELA Grade 1 Module 2 Teacher Guide.pdf"
STANDARDS = SAMPLES / "Grade 1 GA ELA Standards.xlsx"


def main() -> None:
    cfg = Config()

    # 1. Standards spreadsheet -> grade-indexed tree
    if STANDARDS.exists():
        stds = parse_standards(STANDARDS)
        print(f"Standards: {len(stds.standards)} items, grade {stds.grade} ({stds.framework})")

    # 2. Teacher guide -> lessons
    if not GUIDE.exists():
        print("(teacher guide not found; skipping)")
        return
    guide = parse_teacher_guide(GUIDE, cfg)
    print(f"Guide: grade {guide.grade}, module {guide.module}, {len(guide.lessons)} lessons\n")

    # 3. Verify before trusting
    with PdfDocument(GUIDE) as doc:
        report = verify(guide, doc=doc, cfg=cfg, expected_count=40)
    print(report.render())
    print()

    # 4. Show one fully-parsed lesson
    first = guide.lessons[0]
    print(f"Example lesson {first.code} — {first.title}")
    print(f"  pages           : {first.page_start}-{first.page_end}")
    print(f"  declared (claim): {', '.join(first.declared_standards)}")
    print(f"  learning targets: {len(first.learning_targets)}")
    for t in first.learning_targets:
        print(f"    - {t.text}  {t.codes}")
    print(f"  agenda          : {len(first.agenda)} blocks, {first.total_minutes} min")
    for a in first.agenda:
        print(f"    {a.section:<22} {a.letter}  {a.minutes:>2}m  {a.title[:44]}")


if __name__ == "__main__":
    main()
