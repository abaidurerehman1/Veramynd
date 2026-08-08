"""Offline Step-7 shortlist rescue sweep from cached retrieve JSON.

Recomputes final top-50 under ``shortlist_rescue_slots`` without re-running
embedding / BM25 / CE. Gold is eval-only (metrics only).

Example:
  python -m veramynd_parser.scripts.eval_shortlist_rescue \\
    --gold output/reports/gold_set_batch1.jsonl \\
    --retrieve-dir output/retrieve \\
    --out output/reports/shortlist_rescue_eval.json
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT.parent))

from dataclasses import fields

from veramynd_parser.retrieve.gold_metrics import _load_gold_pairs
from veramynd_parser.retrieve.models import Candidate
from veramynd_parser.retrieve.pipeline import (
    DEFAULT_JUDGE_SHORTLIST_K,
    DEFAULT_PARENT_CAP,
    DEFAULT_SHORTLIST_PRESERVE_RRF,
    DEFAULT_SHORTLIST_RRF_WEIGHT,
    build_judge_shortlist,
)

DEFAULT_RESCUE_SWEEP = (0, 3, 5, 8, 10)
DEFAULT_CUTOFFS = (10, 20, 30, 40, 50)


def _candidate_from_dict(row: dict[str, Any]) -> Candidate:
    known = {f.name for f in fields(Candidate)}
    payload = {k: v for k, v in row.items() if k in known}
    return Candidate(**payload)


def _recall_at(
    ranked_codes: list[str],
    gold_codes: list[str],
    cutoffs: tuple[int, ...],
) -> dict[str, Any]:
    hits = {k: 0 for k in cutoffs}
    rr_sum = 0.0
    ranks: dict[str, int | None] = {}
    for code in gold_codes:
        if code in ranked_codes:
            rank = ranked_codes.index(code) + 1
            ranks[code] = rank
            rr_sum += 1.0 / rank
            for k in cutoffs:
                if rank <= k:
                    hits[k] += 1
        else:
            ranks[code] = None
    n = len(gold_codes)
    return {
        "n_positives": n,
        "mrr": round(rr_sum / n, 4) if n else 0.0,
        "gold_ranks": ranks,
        "recall": {
            f"@{k}": {
                "hits": hits[k],
                "n": n,
                "rate": round(hits[k] / n, 4) if n else 0.0,
            }
            for k in cutoffs
        },
    }


def _load_lists(
    payload: dict[str, Any],
) -> tuple[list[Candidate], list[Candidate], int, float, int]:
    reranked = [_candidate_from_dict(r) for r in (payload.get("reranked_candidates") or [])]
    merged = [_candidate_from_dict(r) for r in (payload.get("rrf_candidates") or [])]
    # Explicit None checks: a run made with e.g. --shortlist-rrf-weight 0 stores
    # a falsy 0.0 that `or DEFAULT` would silently replace, so the sweep would
    # no longer replay the live shortlist it claims to replay.
    raw_top_n = payload.get("judge_shortlist_k")
    top_n = int(raw_top_n) if raw_top_n is not None else DEFAULT_JUDGE_SHORTLIST_K
    raw_weight = payload.get("shortlist_rrf_weight")
    rrf_weight = (
        float(raw_weight) if raw_weight is not None else DEFAULT_SHORTLIST_RRF_WEIGHT
    )
    raw_cap = payload.get("parent_cap")
    parent_cap = int(raw_cap) if raw_cap is not None else DEFAULT_PARENT_CAP
    return reranked, merged, top_n, rrf_weight, parent_cap


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Offline shortlist-rescue sweep from retrieve cache")
    p.add_argument("--gold", default="output/reports/gold_set_batch1.jsonl")
    p.add_argument("--retrieve-dir", default="output/retrieve")
    p.add_argument("--out", default="output/reports/shortlist_rescue_eval.json")
    p.add_argument(
        "--rescue-slots",
        type=int,
        nargs="+",
        default=list(DEFAULT_RESCUE_SWEEP),
        help="sweep values for shortlist_rescue_slots",
    )
    args = p.parse_args(argv)

    gold_rows = _load_gold_pairs(args.gold)
    gold_by_lesson: dict[str, list[str]] = defaultdict(list)
    for row in gold_rows:
        rid = row["resource_id"]
        code = row["standard_code"]
        if code not in gold_by_lesson[rid]:
            gold_by_lesson[rid].append(code)

    retrieve_dir = Path(args.retrieve_dir)
    cutoffs = DEFAULT_CUTOFFS
    sweep = [int(n) for n in args.rescue_slots]
    if 0 not in sweep:
        sweep = [0] + sweep

    per_n: dict[str, Any] = {}
    baseline_misses: dict[str, list[str]] = {}  # rid -> gold codes missing @50 at N=0

    for n in sweep:
        hit_counts = {k: 0 for k in cutoffs}
        rr_sum = 0.0
        n_pos = 0
        missing_files = 0
        per_lesson: dict[str, Any] = {}
        recovered_via_rescue = 0
        recovered_already_in_core = 0
        recovered_via_filler = 0
        still_missing = 0
        rescue_marker_ok = 0
        recall10_flat_check: list[bool] = []

        for rid, gold_codes in sorted(gold_by_lesson.items()):
            path = retrieve_dir / f"{rid}.json"
            if not path.is_file():
                missing_files += len(gold_codes)
                per_lesson[rid] = {"error": "missing_retrieve"}
                continue
            payload = json.loads(path.read_text(encoding="utf-8"))
            reranked, merged, top_n, rrf_weight, parent_cap = _load_lists(payload)
            if not reranked or not merged:
                missing_files += len(gold_codes)
                per_lesson[rid] = {"error": "empty_candidates"}
                continue

            shortlist = build_judge_shortlist(
                reranked,
                merged,
                top_n=top_n,
                rrf_weight=rrf_weight,
                parent_cap=parent_cap,
                preserve_rrf_top=DEFAULT_SHORTLIST_PRESERVE_RRF,
                rescue_slots=n,
            )
            ranked = [c.standard_code for c in shortlist]
            metrics = _recall_at(ranked, gold_codes, cutoffs)
            rescued_rows = [
                {
                    "standard_code": c.standard_code,
                    "final_rank": c.final_rank,
                    "sum_rank": c.sum_rank,
                    "rrf_rank": c.rrf_rank,
                    "rerank_rank": c.rerank_rank,
                    "rescued_via": c.rescued_via,
                }
                for c in shortlist
                if c.rescued_via
            ]

            # Core-order check vs N=0 for this lesson (when n>0).
            core_ok = None
            recall10_vs_baseline = None
            if n > 0:
                base_sl = build_judge_shortlist(
                    reranked,
                    merged,
                    top_n=top_n,
                    rrf_weight=rrf_weight,
                    parent_cap=parent_cap,
                    preserve_rrf_top=DEFAULT_SHORTLIST_PRESERVE_RRF,
                    rescue_slots=0,
                )
                core_n = top_n - n
                core_ok = [c.standard_code for c in shortlist[:core_n]] == [
                    c.standard_code for c in base_sl[:core_n]
                ]
                base_ranked = [c.standard_code for c in base_sl]
                base_m = _recall_at(base_ranked, gold_codes, cutoffs)
                recall10_vs_baseline = (
                    metrics["recall"]["@10"]["hits"] == base_m["recall"]["@10"]["hits"]
                )
                recall10_flat_check.append(bool(recall10_vs_baseline))

                # Track recovery of golds that missed @50 at N=0.
                if rid not in baseline_misses:
                    baseline_misses[rid] = [
                        code
                        for code, rank in base_m["gold_ranks"].items()
                        if rank is None or rank > 50
                    ]
                for code in baseline_misses.get(rid, []):
                    new_rank = metrics["gold_ranks"].get(code)
                    if new_rank is not None and new_rank <= 50:
                        # Credit rescue only when the marker proves it —
                        # unmarked re-entries are fused-tail fillers, and
                        # counting them inflated the rescue headline number.
                        cand = next(
                            (c for c in shortlist if c.standard_code == code),
                            None,
                        )
                        if cand is not None and cand.rescued_via == "sum":
                            recovered_via_rescue += 1
                            rescue_marker_ok += 1
                        elif cand is not None and (cand.final_rank or 999) <= (top_n - n):
                            recovered_already_in_core += 1
                        else:
                            recovered_via_filler += 1
                    else:
                        still_missing += 1

            for code in gold_codes:
                n_pos += 1
                rank = metrics["gold_ranks"].get(code)
                if rank is not None:
                    rr_sum += 1.0 / rank
                    for cutoff in cutoffs:
                        if rank <= cutoff:
                            hit_counts[cutoff] += 1

            if n == 0:
                baseline_misses[rid] = [
                    code
                    for code, rank in metrics["gold_ranks"].items()
                    if rank is None or rank > 50
                ]

            per_lesson[rid] = {
                "n_shortlist": len(shortlist),
                "core_order_matches_baseline": core_ok,
                "recall10_matches_baseline": recall10_vs_baseline,
                "rescued": rescued_rows,
                **metrics,
            }

        n0_miss_total = sum(len(v) for v in baseline_misses.values())
        per_n[str(n)] = {
            "shortlist_rescue_slots": n,
            "missing_file_positives": missing_files,
            "baseline_misses_at_50": n0_miss_total if n == 0 else None,
            "recovery_of_baseline_misses": (
                None
                if n == 0
                else {
                    "baseline_miss_n": n0_miss_total,
                    "recovered_via_sum_rescue": recovered_via_rescue,
                    "recovered_already_in_core": recovered_already_in_core,
                    "recovered_via_fused_tail_filler": recovered_via_filler,
                    "still_missing": still_missing,
                    "rescue_marker_confirmed": rescue_marker_ok,
                }
            ),
            "recall10_flat_across_lessons": (
                None
                if n == 0
                else {
                    "all_flat": all(recall10_flat_check) if recall10_flat_check else True,
                    "lessons_checked": len(recall10_flat_check),
                    "lessons_flat": sum(1 for x in recall10_flat_check if x),
                }
            ),
            "aggregated": {
                "n_positives": n_pos,
                "mrr": round(rr_sum / n_pos, 4) if n_pos else 0.0,
                "recall": {
                    f"@{c}": {
                        "hits": hit_counts[c],
                        "n": n_pos,
                        "rate": round(hit_counts[c] / n_pos, 4) if n_pos else 0.0,
                    }
                    for c in cutoffs
                },
            },
            "per_lesson": per_lesson,
        }

    # Honest @10 flat summary across the sweep (vs N=0 rates).
    base_rate = (per_n.get("0") or {}).get("aggregated", {}).get("recall", {}).get("@10", {})
    flat_summary = []
    for n in sweep:
        rate = per_n[str(n)]["aggregated"]["recall"]["@10"]
        flat_summary.append(
            {
                "n": n,
                "recall_at_10": rate,
                "flat_vs_n0": rate.get("hits") == base_rate.get("hits"),
            }
        )

    out = {
        "sweep": sweep,
        "note": (
            "Replays build_judge_shortlist on cached reranked_candidates + "
            "rrf_candidates. Gold is read-only for metrics. "
            "Recall@10 is expected to stay flat for N<=10 because core slots "
            "are the fused top-(50-N); this report verifies that explicitly."
        ),
        "recall10_flat_summary": flat_summary,
        "by_rescue_slots": per_n,
    }
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"wrote": str(out_path), "recall10_flat_summary": flat_summary}, indent=2))
    for n in sweep:
        agg = per_n[str(n)]["aggregated"]["recall"]
        rec = per_n[str(n)].get("recovery_of_baseline_misses")
        print(
            f"N={n}: @10={agg['@10']['rate']:.2%} @50={agg['@50']['rate']:.2%}"
            + (f" recovered_via_rescue={rec}" if rec else ""),
            flush=True,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
