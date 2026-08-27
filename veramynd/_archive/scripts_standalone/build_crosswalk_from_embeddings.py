#!/usr/bin/env python3
"""Build a source-standard -> target-standard crosswalk from OpenAI
embedding similarity between the two standards' own official wording.
No hardcoded mappings.

This is the third crosswalk-building approach tried in this codebase:
  1. A hand-authored Python dict of verified matches -- accurate, but baked
     one person's judgment into code; doesn't generalize. Deleted.
  2. A retrieval co-occurrence / "lift" statistic across lessons -- fully
     dynamic, validated and REJECTED (0-1/24 correct at 40-lesson scale).
  3. Bag-of-words IDF-weighted cosine similarity
     (build_crosswalk_from_text.py) -- validated and WORKING, but capped by
     surface-word overlap: two standards that say the same thing in
     different words (paraphrase, synonym, different scaffolding phrasing)
     score low even though they're a correct match. Ceiling on this repo's
     19-pair ground truth: 13/19 top-1 (68%), 15/19 top-3 (79%).
  4. THIS FILE: same shape, but the similarity signal is OpenAI
     text-embedding-3-large cosine distance instead of word overlap --
     the same embedding model the core RAG pipeline already uses for
     lesson-to-standard retrieval, reused here rather than reinvented.
     Embeddings capture paraphrase/synonym relationships that bag-of-words
     cannot. Validated on the same 19-pair ground truth as approach 3 (see
     tests/test_build_crosswalk_from_embeddings.py) as a live-API test,
     skipped when OPENAI_API_KEY is not set.

Requires OPENAI_API_KEY (via env or veramynd_parser's normal .env loading).
Makes one embeddings API call per side (source texts, target texts) --
cheap: a few dozen short strings, not a bulk lesson corpus.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

_PKG_ROOT = Path(__file__).resolve().parent.parent
if str(_PKG_ROOT) not in sys.path:
    sys.path.insert(0, str(_PKG_ROOT))

from veramynd_parser.embed.runner import DEFAULT_EMBEDDING_MODEL, openai_embed_texts  # noqa: E402
from veramynd_parser.normalize.llm import openai_api_key  # noqa: E402


def load_target_texts(standards_dir: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    for f in sorted(standards_dir.glob("*.json")):
        data = json.loads(f.read_text(encoding="utf-8"))
        code = data.get("standard_code")
        if not code:
            continue
        text = (data.get("raw_text") or "").strip() or (data.get("competency_statement") or "").strip()
        if text:
            out[code] = text
    return out


def load_source_rows(source_csv: Path) -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = []
    with source_csv.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            rows.append((row["source_code"].strip(), row["source_text"].strip()))
    return rows


def cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(y * y for y in b) ** 0.5
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


# Calibrated against this repo's 19-pair hand-verified ground truth
# (crosswalk_grade1_unit1_verified.csv) -- text-embedding-3-large cosine
# similarity between genuinely-matching standard pairs clusters well above
# the bag-of-words tiers used for build_crosswalk_from_text.py, and
# unrelated pairs cluster lower but not near zero (embeddings of short,
# similarly-phrased curriculum standards are never orthogonal). Re-run
# tests/test_build_crosswalk_from_embeddings.py::test_calibration_report
# against a larger ground truth before reusing these cutoffs for a
# different grade/subject -- they are data, not a universal constant.
HIGH_CONFIDENCE_MIN = 0.60
MEDIUM_CONFIDENCE_MIN = 0.50


def confidence_tier(score: float) -> str:
    if score >= HIGH_CONFIDENCE_MIN:
        return "high"
    if score >= MEDIUM_CONFIDENCE_MIN:
        return "medium"
    return "low"


def build_crosswalk(
    source_rows: list[tuple[str, str]],
    target_texts: dict[str, str],
    *,
    model: str = DEFAULT_EMBEDDING_MODEL,
    candidates_per_code: int = 3,
    api_key: str | None = None,
) -> list[dict[str, str]]:
    target_codes = list(target_texts.keys())
    source_texts = [text for _code, text in source_rows]

    key = openai_api_key(api_key)
    all_vectors = openai_embed_texts(
        source_texts + [target_texts[c] for c in target_codes],
        model=model,
        api_key=key,
    )
    source_vecs = all_vectors[: len(source_texts)]
    target_vecs = all_vectors[len(source_texts) :]

    rows: list[dict[str, str]] = []
    for (source_code, _source_text), s_vec in zip(source_rows, source_vecs):
        scored = [
            (target_code, cosine(s_vec, t_vec))
            for target_code, t_vec in zip(target_codes, target_vecs)
        ]
        scored.sort(key=lambda t: -t[1])
        for target_code, score in scored[:candidates_per_code]:
            rows.append(
                {
                    "source_code": source_code,
                    "target_code": target_code,
                    "cosine_similarity": f"{score:.4f}",
                    "confidence": confidence_tier(score),
                    "target_standard_text": target_texts[target_code],
                }
            )
    return rows


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--source-csv", required=True, type=Path, help="CSV with columns: source_code, source_text")
    ap.add_argument("--standards-dir", required=True, type=Path, help="target standards dir (normalize output, any framework)")
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--candidates-per-code", type=int, default=3)
    ap.add_argument("--model", default=DEFAULT_EMBEDDING_MODEL)
    args = ap.parse_args(argv)

    target_texts = load_target_texts(args.standards_dir)
    source_rows = load_source_rows(args.source_csv)

    rows = build_crosswalk(
        source_rows,
        target_texts,
        model=args.model,
        candidates_per_code=args.candidates_per_code,
    )

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f, fieldnames=["source_code", "target_code", "cosine_similarity", "confidence", "target_standard_text"]
        )
        writer.writeheader()
        writer.writerows(rows)

    n_high = sum(1 for r in rows if r["confidence"] == "high")
    print(f"Proposed mappings: {len(rows)} (top-{args.candidates_per_code} per source code)")
    print(f"High-confidence rows: {n_high}")
    print(f"Wrote {args.out}")


if __name__ == "__main__":
    main()
