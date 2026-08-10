#!/usr/bin/env python3
"""Export the top-50 retrieved standards per lesson to one CSV per lesson.

Columns: rank, standard_code, standard_text
- rank: 1-indexed position in the retrieve pipeline's ranked candidate list
  (post-rerank when available, i.e. the `candidates` field of the retrieve
  JSON -- this is the pipeline's final ordering, same one recall@k is scored
  against).
- standard_code: the CCSS-style code.
- standard_text: the publisher's official standard text (raw_text) from the
  normalized standards record; falls back to competency_statement, then to
  the first line of the embed text, if raw_text is missing.
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

REPO = Path("/Users/harris/Downloads/Veramynd/Veramynd-shortlist-sum-rescue/veramynd/veramynd_parser")
RETRIEVE_DIR = REPO / "output" / "retrieve_tuned"
STANDARDS_DIR = REPO / "output" / "normalize_standards"
OUT_DIR = REPO / "output" / "reports" / "top50_review"
TOP_N = 50

_standard_text_cache: dict[str, str] = {}


def standard_text(code: str) -> str:
    if code in _standard_text_cache:
        return _standard_text_cache[code]
    path = STANDARDS_DIR / f"{code}.json"
    text = ""
    if path.is_file():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            data = {}
        text = (
            (data.get("raw_text") or "").strip()
            or (data.get("competency_statement") or "").strip()
        )
        if not text:
            embed = (data.get("embed_text") or "").strip()
            text = embed.splitlines()[0] if embed else ""
    if not text:
        text = "(standard text not found)"
    _standard_text_cache[code] = text
    return text


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    retrieve_files = sorted(RETRIEVE_DIR.glob("*.json"))
    written = []
    for path in retrieve_files:
        lesson_code = path.stem
        data = json.loads(path.read_text(encoding="utf-8"))
        candidates = data.get("candidates") or []
        rows = candidates[:TOP_N]
        out_path = OUT_DIR / f"{lesson_code}_top50.csv"
        with out_path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            # NOTE: multi-query retrieve, merge-aggregation=top_k_sum
            # (--merge-top-arms 2), shortlist-rescue-slots=8 — the documented
            # production profile. Only the final cross-encoder rerank step is
            # skipped (no Hugging Face access in this environment); RRF order
            # is used in its place, so exact positions within the top 50 may
            # shift slightly under the real reranker, but the candidate set
            # and its rough ordering should match production closely.
            writer.writerow(["rank", "standard_code", "standard_text"])
            for i, c in enumerate(rows, start=1):
                code = (c.get("standard_code") or "").strip()
                writer.writerow([i, code, standard_text(code)])
        written.append((lesson_code, len(rows)))

    print(f"Wrote {len(written)} lesson CSVs to {OUT_DIR}")
    short = [f"{lc} ({n})" for lc, n in written if n < TOP_N]
    if short:
        print(f"Lessons with fewer than {TOP_N} candidates: {short}")


if __name__ == "__main__":
    main()
