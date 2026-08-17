"""Phase 8 regression helper: GA parse GO + gold4 R@25 gate."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]  # veramynd_parser package root
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from veramynd_parser.standards.semantic import StandardsSemanticAssist
from veramynd_parser.standards.spreadsheet import parse_standards_ex
from veramynd_parser.standards.verify import verify_standards

REPO = ROOT.parent
GOLD = REPO / "docs" / "_ga_g1_module2_goldset.md"
GA = REPO / "data" / "samples" / "Grade 1 GA ELA Standards.xlsx"
GOLD4 = ROOT / "output" / "retrieve_gold4"
CUTOFFS = (10, 20, 25, 30, 50)


def load_positives() -> list[dict]:
    text = GOLD.read_text(encoding="utf-8")
    pat_header = re.compile(
        r"###\s*`GA1-M2-(\d+)`\s*[\u2014\u2013\-]\s*`([0-9A-Za-z.]+)`\s*\([^)]*\)\s*"
        r"(?:\u2192|->)\s*\*\*(FULL|PARTIAL|NONE)\*\*",
        re.I,
    )
    pat_lesson = re.compile(
        r"\*\*Lesson:\*\*\s*Unit\s*(\d+),\s*Lesson\s*(\d+)", re.I
    )
    records: list[dict] = []
    for m in pat_header.finditer(text):
        lm = pat_lesson.search(text[m.end() : m.end() + 500])
        assert lm
        unit, lesson = int(lm.group(1)), int(lm.group(2))
        records.append(
            {
                "gold_id": f"GA1-M2-{m.group(1)}",
                "standard_code": m.group(2),
                "status": m.group(3).lower(),
                "resource_id": f"G1M2U{unit}L{lesson}",
            }
        )
    return [r for r in records if r["status"] in ("full", "partial")]


def check_ga() -> int:
    if not GA.is_file():
        print(f"SKIP GA sample missing: {GA}")
        return 0
    parsed = parse_standards_ex(
        GA, framework="GA ELA", assist=StandardsSemanticAssist(enabled=False)
    )
    report = verify_standards(parsed)
    print(
        f"GA parse: rows={len(parsed.tree.standards)} adapter={parsed.adapter_name} "
        f"hierarchy={parsed.hierarchy_method} verdict={report.verdict}"
    )
    if report.verdict != "GO":
        print(report.render())
        return 1
    if len(parsed.tree.standards) != 188:
        print(f"FAIL: expected 188 GA rows, got {len(parsed.tree.standards)}")
        return 1
    return 0


def check_r25() -> int:
    if not GOLD.is_file():
        print(f"FAIL: goldset missing {GOLD}")
        return 1
    if not GOLD4.is_dir():
        print(f"FAIL: retrieve_gold4 missing {GOLD4}")
        return 1
    positives = load_positives()
    n = len(positives)
    hits = {k: 0 for k in CUTOFFS}
    misses25: list[str] = []
    for g in positives:
        path = GOLD4 / f"{g['resource_id']}.json"
        if not path.is_file():
            print(f"FAIL: missing retrieve json {path}")
            return 1
        data = json.loads(path.read_text(encoding="utf-8"))
        codes = [
            (c.get("standard_code") or "").strip()
            for c in (data.get("candidates") or [])
        ]
        code = g["standard_code"]
        rank = codes.index(code) + 1 if code in codes else None
        for k in hits:
            if rank is not None and rank <= k:
                hits[k] += 1
        if rank is None or rank > 25:
            misses25.append(
                f"{g['gold_id']} {g['resource_id']} {code} rank={rank}"
            )
    print(f"gold4 positives={n}")
    for k in CUTOFFS:
        print(f"  Recall@{k}: {hits[k]}/{n} = {hits[k]/n:.1%}")
    if hits[25] != n:
        print("FAIL protected bar R@25 != 100%")
        for line in misses25:
            print(f"  miss: {line}")
        return 1
    print("PASS protected bar R@25 == 100%")
    return 0


def main() -> int:
    rc = 0
    rc |= check_ga()
    rc |= check_r25()
    return rc


if __name__ == "__main__":
    sys.exit(main())
