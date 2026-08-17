"""Batch-1 gold recall at R@10/20/25/30/50 for enterprise shortlist depth.

Protected Batch-1 bar: Recall@25 = 100% on retrieve_gold4 (do not tune retrieve
to hide parser regressions).
"""
from __future__ import annotations

import json
import re
from collections import defaultdict
from pathlib import Path

GOLD = Path(__file__).resolve().parents[3] / "docs" / "_ga_g1_module2_goldset.md"
BASE = Path(__file__).resolve().parents[2] / "output"
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


def main() -> None:
    positives = load_positives()
    n = len(positives)
    for name in ("retrieve_gold4", "retrieve_tuned"):
        retdir = BASE / name
        if not retdir.is_dir():
            print(f"=== {name} === SKIP (missing {retdir})")
            continue
        sample_path = retdir / "G1M2U1L1.json"
        if not sample_path.is_file():
            print(f"=== {name} === SKIP (no sample json)")
            continue
        sample = json.loads(sample_path.read_text(encoding="utf-8"))
        hits = {k: 0 for k in CUTOFFS}
        details: list[tuple[dict, int | None]] = []
        by_lesson: dict[str, list] = defaultdict(list)
        for g in positives:
            data = json.loads(
                (retdir / f"{g['resource_id']}.json").read_text(encoding="utf-8")
            )
            codes = [
                (c.get("standard_code") or "").strip()
                for c in (data.get("candidates") or [])
            ]
            code = g["standard_code"]
            rank = codes.index(code) + 1 if code in codes else None
            for k in hits:
                if rank is not None and rank <= k:
                    hits[k] += 1
            details.append((g, rank))
            by_lesson[g["resource_id"]].append((g, rank))

        print(f"=== {name} ===")
        print(
            "config merge=",
            sample.get("merge_aggregation"),
            "rescue=",
            sample.get("shortlist_rescue_slots"),
            "skip_rerank=",
            sample.get("skip_rerank"),
            "blend=",
            sample.get("blend_rrf"),
        )
        for k in CUTOFFS:
            print(f"  Recall@{k}: {hits[k]}/{n} = {hits[k]/n:.1%}")
        r25 = hits[25] / n if n else 0.0
        if name == "retrieve_gold4":
            status = "PASS" if r25 >= 1.0 else "FAIL"
            print(f"  protected bar R@25 == 100%: {status}")
        print("  per-lesson R@20:")
        for lid in sorted(by_lesson):
            rows = by_lesson[lid]
            h = sum(1 for _g, r in rows if r and r <= 20)
            print(f"    {lid}: {h}/{len(rows)} = {h/len(rows):.1%}")
        print("  misses @20:")
        for g, rank in details:
            if rank is None or rank > 20:
                print(
                    f"    {g['gold_id']} {g['resource_id']} {g['standard_code']} "
                    f"{g['status']} rank={rank}"
                )
        print("  misses @25:")
        for g, rank in details:
            if rank is None or rank > 25:
                print(
                    f"    {g['gold_id']} {g['resource_id']} {g['standard_code']} "
                    f"{g['status']} rank={rank}"
                )
        print()


if __name__ == "__main__":
    main()
