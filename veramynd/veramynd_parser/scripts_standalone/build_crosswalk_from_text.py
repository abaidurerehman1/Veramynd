#!/usr/bin/env python3
"""Build a source-standard -> target-standard crosswalk from TEXT SIMILARITY
between the two standards' own official wording. No hardcoded mappings.

This replaces two earlier, rejected approaches:
  1. A hand-authored Python dict of verified matches -- accurate, but baked
     one person's specific judgment calls into code; doesn't generalize.
  2. A retrieval co-occurrence / "lift" statistic across lessons -- fully
     dynamic, but validated against the hand-verified table and it failed
     badly (0-1 of 24 correct) because 40 lessons is too small a sample for
     the statistics to separate signal from noise. Recorded here so nobody
     re-attempts it expecting it to work at small corpus scale.

METHOD (this version)
----------------------
Bag-of-words cosine similarity between:
  - the SOURCE standard's own official text (supplied via --source-csv --
    e.g. the public CCSS text for whichever codes are in scope; this is
    reference DATA, analogous to the target standards spreadsheet, not
    application logic -- swap it for a different grade/subject/framework
    and the tool works unchanged)
  - every TARGET standard's raw_text / competency_statement (read from
    --standards-dir, already produced by the ordinary normalize pipeline for
    any target standards set)

No API key, no internet access, and no lesson-retrieval evidence required --
this only needs the two standard sets' own text, which is the actual
ground truth for whether two standards describe the same skill.

OUTPUT
------
CSV: one row per (source_code, proposed target_code), ranked by cosine
similarity, with the top N candidates per source code for human review.
Still a PROPOSAL, tiered by confidence -- text similarity catches "these
say almost the same thing" reliably, but two standards can genuinely
correspond while using very different wording (GA often generalizes or
splits a CCSS target), which similarity alone won't always catch. Low/no
matches should go to a human, not be silently dropped.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
from pathlib import Path

_STOPWORDS = {
    "a", "an", "the", "and", "or", "of", "to", "in", "on", "with", "for",
    "by", "as", "is", "are", "be", "that", "this", "their", "its", "at",
    "from", "into", "when", "which", "such",
}


def tokenize(text: str) -> list[str]:
    # Parenthetical scaffolding tags ("(Introduce)", "(I/C)", "(Master)") are
    # curriculum-authoring metadata, not standard content -- strip before
    # tokenizing so words like "continue"/"master" never enter the vectors.
    text = re.sub(r"\([^)]*\)", " ", text)
    words = re.findall(r"[a-z']+", text.lower())
    return [w for w in words if w not in _STOPWORDS and len(w) > 1]


def find_collocations(token_lists: list[list[str]], min_ratio: float = 0.7) -> set[tuple[str, str]]:
    """Detect word pairs that almost always appear adjacent to each other
    across the corpus (e.g. "frequently"+"occurring") and merge them into one
    token. Computed fresh from whatever corpus is passed in -- not a fixed
    phrase list -- so it adapts to any framework's own scaffolding language.

    Rationale: bag-of-words cosine treats "frequently" and "occurring" as two
    INDEPENDENT matching dimensions. If they're really a fixed collocation,
    that double-counts one signal as two, letting a target that merely shares
    the boilerplate phrase out-score a target that shares the one word that
    actually carries the standard's meaning (validated failure: L.1.1f
    'frequently occurring ADJECTIVES' vs. GA's 'frequently occurring
    PREPOSITIONS' -- the shared scaffolding phrase beat the one real
    content word). Collapsing the pair into one token removes the
    double-count.
    """
    from collections import Counter

    unigram_df: Counter[str] = Counter()
    bigram_df: Counter[tuple[str, str]] = Counter()
    for tokens in token_lists:
        for w in set(tokens):
            unigram_df[w] += 1
        for pair in set(zip(tokens, tokens[1:])):
            bigram_df[pair] += 1

    collocations: set[tuple[str, str]] = set()
    for (w1, w2), df_pair in bigram_df.items():
        if df_pair < 2:
            continue  # a single shared instance isn't evidence of a fixed phrase
        if df_pair / unigram_df[w1] >= min_ratio and df_pair / unigram_df[w2] >= min_ratio:
            collocations.add((w1, w2))
    return collocations


def apply_collocations(tokens: list[str], collocations: set[tuple[str, str]]) -> list[str]:
    out: list[str] = []
    i = 0
    while i < len(tokens):
        if i + 1 < len(tokens) and (tokens[i], tokens[i + 1]) in collocations:
            out.append(f"{tokens[i]}_{tokens[i+1]}")
            i += 2
        else:
            out.append(tokens[i])
            i += 1
    return out


def cosine_sim(a_tokens: list[str], b_tokens: list[str], idf: dict[str, float]) -> float:
    """IDF-weighted cosine similarity.

    Validated need: plain (unweighted) term overlap gives a false-positive
    "high confidence" match between L.1.1f ('frequently occurring
    adjectives') and 1.L.GC.1.16 ('frequently occurring prepositions') --
    they share the boilerplate phrase "frequently occurring", used across
    MANY unrelated Grade-1 GA standards, while disagreeing on the one word
    that actually carries the meaning (adjectives vs. prepositions). IDF
    down-weights exactly that kind of corpus-wide-common word and up-weights
    the rare, content-bearing ones -- the same fix search engines use so
    "the" doesn't dominate relevance over the word that actually matters.
    """
    if not a_tokens or not b_tokens:
        return 0.0
    from collections import Counter

    ca, cb = Counter(a_tokens), Counter(b_tokens)
    shared = set(ca) & set(cb)
    dot = sum(ca[w] * cb[w] * idf.get(w, 1.0) ** 2 for w in shared)
    norm_a = sum((v * idf.get(w, 1.0)) ** 2 for w, v in ca.items()) ** 0.5
    norm_b = sum((v * idf.get(w, 1.0)) ** 2 for w, v in cb.items()) ** 0.5
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def build_idf(token_lists: list[list[str]]) -> dict[str, float]:
    """Standard IDF: log(N / doc_freq), computed over the TARGET corpus (the
    larger, more stable side) so it reflects genuine corpus-wide commonness
    rather than the small source list's own word distribution."""
    import math
    from collections import Counter

    doc_freq: Counter[str] = Counter()
    for tokens in token_lists:
        for w in set(tokens):
            doc_freq[w] += 1
    n = len(token_lists) or 1
    return {w: math.log(n / df) + 0.1 for w, df in doc_freq.items()}


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


def confidence_tier(score: float) -> str:
    if score >= 0.45:
        return "high"
    if score >= 0.25:
        return "medium"
    return "low"


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--source-csv", required=True, type=Path, help="CSV with columns: source_code, source_text")
    ap.add_argument("--standards-dir", required=True, type=Path, help="target standards dir (normalize output, any framework)")
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--candidates-per-code", type=int, default=3)
    args = ap.parse_args(argv)

    target_texts = load_target_texts(args.standards_dir)
    target_tokens_raw = {code: tokenize(text) for code, text in target_texts.items()}

    source_rows_raw: list[tuple[str, list[str]]] = []
    with args.source_csv.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            source_rows_raw.append((row["source_code"].strip(), tokenize(row["source_text"])))

    # Detect collocations over BOTH corpora combined -- a scaffolding phrase
    # can be a fixed pair within just the source framework's writing style,
    # just the target's, or both, and either case causes the same
    # double-counting bug if left as two separate unigrams.
    all_token_lists = list(target_tokens_raw.values()) + [toks for _c, toks in source_rows_raw]
    collocations = find_collocations(all_token_lists)

    target_tokens = {code: apply_collocations(toks, collocations) for code, toks in target_tokens_raw.items()}
    idf = build_idf(list(target_tokens.values()))

    if collocations:
        print(f"Detected {len(collocations)} collocation(s), merged before scoring: "
              f"{sorted(f'{a}_{b}' for a, b in collocations)}")

    rows: list[dict[str, str]] = []
    for source_code, source_tokens_raw_ in source_rows_raw:
        source_tokens = apply_collocations(source_tokens_raw_, collocations)
        scored = [
            (target_code, cosine_sim(source_tokens, ttoks, idf))
            for target_code, ttoks in target_tokens.items()
        ]
        scored.sort(key=lambda t: -t[1])
        for target_code, score in scored[: args.candidates_per_code]:
            rows.append(
                {
                    "source_code": source_code,
                    "target_code": target_code,
                    "cosine_similarity": f"{score:.3f}",
                    "confidence": confidence_tier(score),
                    "target_standard_text": target_texts[target_code],
                }
            )

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f, fieldnames=["source_code", "target_code", "cosine_similarity", "confidence", "target_standard_text"]
        )
        writer.writeheader()
        writer.writerows(rows)

    n_high = sum(1 for r in rows if r["confidence"] == "high")
    print(f"Proposed mappings: {len(rows)} (high-confidence top-1s among them: see CSV)")
    print(f"High-confidence rows overall: {n_high}")
    print(f"Wrote {args.out}")


if __name__ == "__main__":
    main()
