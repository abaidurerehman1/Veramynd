"""Validate Liz top-50 CSVs."""
from __future__ import annotations

import csv
import json
from collections import Counter
from pathlib import Path

OUT = Path("output/reports/liz_top50_review")
STD = Path("output/normalize_standards")
LESSONS = ["G1M2U1L1", "G1M2U1L3", "G1M2U1L6", "G1M2U3L5"]


def text_key(t: str) -> str:
    return " ".join((t or "").lower().split()).rstrip(" .;")


def main() -> None:
    ok = True
    for lid in LESSONS:
        path = OUT / f"{lid}_top50.csv"
        rows = list(csv.DictReader(path.open(encoding="utf-8-sig")))
        cols = list(rows[0].keys()) if rows else []
        print(f"=== {lid} ===")
        print(f"  rows {len(rows)} cols {cols}")

        if cols != ["rank", "standard_code", "standard_text"]:
            print("  FAIL bad columns")
            ok = False

        ranks = [int(r["rank"]) for r in rows]
        if ranks != list(range(1, 51)):
            print("  FAIL ranks", ranks[:3], ranks[-3:])
            ok = False
        else:
            print("  ranks 1..50 OK")

        codes = [r["standard_code"].strip() for r in rows]
        texts = [r["standard_text"].strip() for r in rows]
        if any(not c for c in codes):
            print("  FAIL empty code")
            ok = False
        if any(not t for t in texts):
            print("  FAIL empty text")
            ok = False

        if len(codes) != len(set(codes)):
            print("  FAIL dup codes", {c: n for c, n in Counter(codes).items() if n > 1})
            ok = False
        else:
            print("  unique codes 50 OK")

        keys = [text_key(t) for t in texts]
        if len(keys) != len(set(keys)):
            print("  FAIL dup texts")
            ok = False
        else:
            print("  unique texts 50 OK")

        bad = []
        mismatch = []
        for r in rows:
            t = r["standard_text"]
            low = t.lower()
            if low.startswith("standard:") or "domain primary:" in low:
                bad.append((r["rank"], r["standard_code"], t[:80]))
            npath = STD / f"{r['standard_code']}.json"
            if npath.is_file():
                raw = (
                    json.loads(npath.read_text(encoding="utf-8")).get("raw_text") or ""
                ).strip()
                if raw != t.strip():
                    mismatch.append((r["rank"], r["standard_code"]))
            else:
                bad.append((r["rank"], r["standard_code"], "missing norm file"))

        if bad:
            print("  FAIL bad text", bad[:5])
            ok = False
        else:
            print("  text quality OK")

        if mismatch:
            print("  FAIL not equal raw_text", mismatch[:5])
            ok = False
        else:
            print("  matches normalize raw_text OK")

    allr = list(
        csv.DictReader((OUT / "ALL_gold_lessons_top50.csv").open(encoding="utf-8-sig"))
    )
    print(f"=== ALL === rows {len(allr)} cols {list(allr[0].keys()) if allr else None}")
    if len(allr) != 200:
        print("  FAIL expected 200")
        ok = False
    if list(allr[0].keys()) != [
        "lesson_id",
        "rank",
        "standard_code",
        "standard_text",
    ]:
        print("  FAIL ALL columns")
        ok = False

    print()
    print("OVERALL", "PASS" if ok else "FAIL")


if __name__ == "__main__":
    main()
