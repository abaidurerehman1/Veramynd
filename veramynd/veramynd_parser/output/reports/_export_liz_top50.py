"""Export top-50 for Liz: rank, standard_code, standard_text only."""
from __future__ import annotations

import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RETRIEVE = ROOT / "output" / "retrieve_gold4"
STANDARDS = ROOT / "output" / "normalize_standards"
OUT_DIR = ROOT / "output" / "reports" / "liz_top50_review"
TOP_N = 50


def load_raw_text(code: str) -> str:
    path = STANDARDS / f"{code}.json"
    if not path.is_file():
        return ""
    data = json.loads(path.read_text(encoding="utf-8"))
    return (data.get("raw_text") or "").strip()


def unique_key_text(text: str) -> str:
    t = " ".join((text or "").lower().split())
    return t.rstrip(" .;")


def build_rows(candidates: list[dict]) -> list[dict]:
    rows: list[dict] = []
    seen_codes: set[str] = set()
    seen_texts: set[str] = set()

    for c in candidates:
        if len(rows) >= TOP_N:
            break
        code = (c.get("standard_code") or "").strip()
        if not code or code in seen_codes:
            continue
        raw = load_raw_text(code)
        if not raw:
            continue
        text_key = unique_key_text(raw)
        if text_key in seen_texts:
            continue
        seen_codes.add(code)
        seen_texts.add(text_key)
        rows.append(
            {
                "rank": len(rows) + 1,
                "standard_code": code,
                "standard_text": raw,
            }
        )
    return rows


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    lessons = sorted(p.stem for p in RETRIEVE.glob("G1*.json"))
    fieldnames = ["rank", "standard_code", "standard_text"]
    all_rows: list[dict] = []

    for lid in lessons:
        data = json.loads((RETRIEVE / f"{lid}.json").read_text(encoding="utf-8"))
        pool = list(data.get("candidates") or [])
        seen = {c.get("standard_code") for c in pool}
        for c in data.get("rrf_candidates") or []:
            code = c.get("standard_code")
            if code and code not in seen:
                pool.append(c)
                seen.add(code)

        rows = build_rows(pool)
        path = OUT_DIR / f"{lid}_top50.csv"
        with path.open("w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=fieldnames)
            w.writeheader()
            w.writerows(rows)
        print(f"wrote {path} n={len(rows)}")
        for r in rows:
            all_rows.append({"lesson_id": lid, **r})

    all_path = OUT_DIR / "ALL_gold_lessons_top50.csv"
    with all_path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["lesson_id", *fieldnames])
        w.writeheader()
        w.writerows(all_rows)
    print(f"wrote {all_path} n={len(all_rows)}")

    (OUT_DIR / "README_for_Liz.txt").write_text(
        "Top 50 retrieved standards per gold lesson.\n"
        "Columns: rank, standard_code, standard_text (official GA wording).\n"
        "Source: output/retrieve_gold4 + normalize_standards raw_text.\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
