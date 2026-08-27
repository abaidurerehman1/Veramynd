#!/usr/bin/env python3
"""Insert crosswalk-confirmed target-standard matches missing from top-N
lists. Fully generic: every path, the crosswalk itself, the insertion rank,
and the list size are supplied as arguments -- nothing about this script is
specific to one grade, subject, publisher, or standards framework. The
crosswalk (which mappings exist, and at what confidence) is DATA, supplied
via --crosswalk; this script contains no mappings of its own.

Crosswalk CSV must have at least: source_code, target_code, confidence
(high/medium/low) -- the shape produced by build_crosswalk_from_text.py, or
a hand-edited/human-reviewed version of it.
"""
from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path


def load_crosswalk(path: Path, min_confidence: str) -> dict[str, list[str]]:
    order = {"low": 0, "medium": 1, "high": 2}
    threshold = order[min_confidence]
    out: dict[str, list[str]] = defaultdict(list)
    with path.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            conf = row.get("confidence", "low").strip().lower()
            if order.get(conf, 0) < threshold:
                continue
            src = row["source_code"].strip()
            tgt = row["target_code"].strip()
            if tgt not in out[src]:
                out[src].append(tgt)
    return out


_text_cache: dict[str, str] = {}


def standard_text(standards_dir: Path, code: str) -> str:
    if code in _text_cache:
        return _text_cache[code]
    path = standards_dir / f"{code}.json"
    text = ""
    if path.is_file():
        data = json.loads(path.read_text(encoding="utf-8"))
        text = (data.get("raw_text") or "").strip() or (data.get("competency_statement") or "").strip()
    _text_cache[code] = text or "(standard text not found)"
    return _text_cache[code]


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--lessons-dir", required=True, type=Path, help="Stage-1 lessons dir (declared_standards source)")
    ap.add_argument("--top-n-dir", required=True, type=Path, help="existing top-N CSVs to correct")
    ap.add_argument("--standards-dir", required=True, type=Path, help="target standards dir (for inserted-row text)")
    ap.add_argument("--crosswalk", required=True, type=Path, help="crosswalk CSV: source_code,target_code,confidence,...")
    ap.add_argument("--out-dir", required=True, type=Path)
    ap.add_argument("--changelog", required=True, type=Path)
    ap.add_argument("--min-confidence", choices=["high", "medium", "low"], default="high")
    ap.add_argument("--insert-at-rank", type=int, default=6)
    ap.add_argument("--top-n", type=int, default=50)
    args = ap.parse_args(argv)

    crosswalk = load_crosswalk(args.crosswalk, args.min_confidence)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    changelog_rows: list[dict[str, str]] = []

    src_files = sorted(args.top_n_dir.glob("*.csv"))
    for src_path in src_files:
        lesson_code = src_path.stem.split("_top")[0]
        lesson_json = args.lessons_dir / f"{lesson_code}.json"
        if not lesson_json.is_file():
            # Not every top-N file necessarily has a matching lesson record
            # in this dir layout -- copy through untouched rather than guess.
            (args.out_dir / src_path.name).write_text(src_path.read_text(encoding="utf-8"), encoding="utf-8")
            continue
        declared = set(json.loads(lesson_json.read_text(encoding="utf-8")).get("declared_standards", []))

        with src_path.open(newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        codes_present = {r["standard_code"] for r in rows}

        missing: list[tuple[str, str]] = []
        for source_code in sorted(declared & crosswalk.keys()):
            for target_code in crosswalk[source_code]:
                if target_code not in codes_present:
                    missing.append((source_code, target_code))
                    codes_present.add(target_code)

        if not missing:
            (args.out_dir / src_path.name).write_text(src_path.read_text(encoding="utf-8"), encoding="utf-8")
            continue

        head = rows[: args.insert_at_rank - 1]
        tail = rows[args.insert_at_rank - 1 :]
        keep_tail = tail[: max(0, args.top_n - len(head) - len(missing))]
        dropped = tail[len(keep_tail) :]

        new_rows = list(head)
        insert_start_rank = len(head) + 1
        for i, (source_code, target_code) in enumerate(missing):
            new_rows.append({"standard_code": target_code, "standard_text": standard_text(args.standards_dir, target_code)})
            changelog_rows.append(
                {
                    "lesson": lesson_code,
                    "action": "added",
                    "standard_code": target_code,
                    "new_rank": str(insert_start_rank + i),
                    "source_target": source_code,
                    "note": f"crosswalk match (confidence >= {args.min_confidence})",
                }
            )
        new_rows.extend(keep_tail)

        out_path = args.out_dir / src_path.name
        with out_path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["rank", "standard_code", "standard_text"])
            for i, r in enumerate(new_rows, start=1):
                writer.writerow([i, r["standard_code"], r["standard_text"]])

        for d in dropped:
            changelog_rows.append(
                {
                    "lesson": lesson_code,
                    "action": "dropped",
                    "standard_code": d["standard_code"],
                    "new_rank": "",
                    "source_target": "",
                    "note": f"lowest-confidence row removed to hold list at {args.top_n} (was rank {d['rank']})",
                }
            )

    args.changelog.parent.mkdir(parents=True, exist_ok=True)
    with args.changelog.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["lesson", "action", "standard_code", "new_rank", "source_target", "note"])
        writer.writeheader()
        writer.writerows(changelog_rows)

    n_changed = len({r["lesson"] for r in changelog_rows if r["action"] == "added"})
    n_added = sum(1 for r in changelog_rows if r["action"] == "added")
    print(f"Lessons changed: {n_changed} / {len(src_files)}")
    print(f"Codes inserted: {n_added}")
    print(f"Wrote {args.out_dir} and {args.changelog}")


if __name__ == "__main__":
    main()
