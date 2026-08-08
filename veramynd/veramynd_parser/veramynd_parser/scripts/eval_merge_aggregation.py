"""Offline recompute of Step-5 merge aggregation modes from cached diagnostics.

Does not re-run embeddings, BM25, or CE. Gold is eval-only (final metrics).

Example:
  python -m veramynd_parser.scripts.eval_merge_aggregation \\
    --gold output/reports/gold_set_batch1.jsonl \\
    --diag-dir output/reports/retrieve_diag \\
    --out output/reports/merge_aggregation_eval.json
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

from veramynd_parser.retrieve.gold_metrics import _load_gold_pairs
from veramynd_parser.retrieve.rrf import (
    MERGE_AGGREGATIONS,
    aggregate_multi_arm_rrf,
    select_merge_pool,
)

# Frozen sweep grid (reported exhaustively; not cherry-picked).
DEFAULT_K_GRID = (40, 60, 80)
DEFAULT_TOP_ARMS_GRID = (1, 2, 3)
DEFAULT_CUTOFFS = (10, 20, 30, 40, 50)


def _lists_from_diag(diag: dict[str, Any]) -> tuple[list[list[str]], list[float], list[str]]:
    per_query = diag.get("per_query") or []
    ranked_lists: list[list[str]] = []
    weights: list[float] = []
    sources: list[str] = []
    for row in per_query:
        if not isinstance(row, dict):
            continue
        codes = [str(c) for c in (row.get("hybrid_codes") or []) if c]
        if not codes:
            continue
        ranked_lists.append(codes)
        # Explicit None check: a stored weight of 0.0 must replay as 0.0
        # (the live aggregator skips zero-weight arms entirely), not be
        # silently swapped for 1.0 by `or`.
        raw_w = row.get("query_weight")
        weights.append(float(raw_w) if raw_w is not None else 1.0)
        sources.append(str(row.get("source") or ""))
    return ranked_lists, weights, sources


def _recall_at(
    ranked_codes: list[str],
    gold_codes: list[str],
    cutoffs: tuple[int, ...],
) -> dict[str, Any]:
    hits = {k: 0 for k in cutoffs}
    rr_sum = 0.0
    for code in gold_codes:
        if code in ranked_codes:
            rank = ranked_codes.index(code) + 1
            rr_sum += 1.0 / rank
            for k in cutoffs:
                if rank <= k:
                    hits[k] += 1
    n = len(gold_codes)
    return {
        "n_positives": n,
        "mrr": round(rr_sum / n, 4) if n else 0.0,
        "recall": {
            f"@{k}": {
                "hits": hits[k],
                "n": n,
                "rate": round(hits[k] / n, 4) if n else 0.0,
            }
            for k in cutoffs
        },
    }


def _configs() -> list[dict[str, Any]]:
    configs: list[dict[str, Any]] = []
    for k in DEFAULT_K_GRID:
        configs.append(
            {
                "label": f"sum_k{k}",
                "aggregation": "sum",
                "k": k,
                "top_arms": 2,
                "log_dampen_base": 2.0,
            }
        )
        configs.append(
            {
                "label": f"max_k{k}",
                "aggregation": "max",
                "k": k,
                "top_arms": 2,
                "log_dampen_base": 2.0,
            }
        )
        configs.append(
            {
                "label": f"log_dampened_k{k}_b2",
                "aggregation": "log_dampened",
                "k": k,
                "top_arms": 2,
                "log_dampen_base": 2.0,
            }
        )
        for n in DEFAULT_TOP_ARMS_GRID:
            configs.append(
                {
                    "label": f"top_k_sum_k{k}_n{n}",
                    "aggregation": "top_k_sum",
                    "k": k,
                    "top_arms": n,
                    "log_dampen_base": 2.0,
                }
            )
    return configs


def _eval_one_pool(
    *,
    gold_by_lesson: dict[str, list[str]],
    diag_dir: Path,
    merge_top_k: int,
    cutoffs: tuple[int, ...],
    aggregation: str,
    top_arms: int,
    k: int,
    pool_membership_mode: str,
    log_dampen_base: float = 2.0,
) -> dict[str, Any]:
    per_lesson: dict[str, Any] = {}
    hit_counts = {c: 0 for c in cutoffs}
    rr_sum = 0.0
    n_pos = 0
    missing = 0
    added_counts: list[int] = []
    pool_sizes: list[int] = []

    for rid, gold_codes in sorted(gold_by_lesson.items()):
        diag_path = diag_dir / f"{rid}.json"
        if not diag_path.is_file():
            missing += len(gold_codes)
            per_lesson[rid] = {"error": "missing_diag"}
            continue
        diag = json.loads(diag_path.read_text(encoding="utf-8"))
        ranked_lists, weights, sources = _lists_from_diag(diag)
        if not ranked_lists:
            missing += len(gold_codes)
            per_lesson[rid] = {"error": "empty_per_query"}
            continue
        primary, _ = aggregate_multi_arm_rrf(
            ranked_lists,
            k=k,
            weights=weights,
            sources=sources,
            aggregation=aggregation,
            top_arms=top_arms,
            log_dampen_base=log_dampen_base,
        )
        secondary = None
        if pool_membership_mode == "union":
            secondary, _ = aggregate_multi_arm_rrf(
                ranked_lists,
                k=k,
                weights=weights,
                sources=sources,
                aggregation="sum",
                top_arms=top_arms,
                log_dampen_base=log_dampen_base,
            )
        pool, stats = select_merge_pool(
            primary,
            merge_top_k=merge_top_k,
            pool_membership_mode=pool_membership_mode,
            secondary_sum_ranked=secondary,
        )
        ranked_codes = [code for code, _s in pool]
        lesson_metrics = _recall_at(ranked_codes, gold_codes, cutoffs)
        pool_hits = sum(1 for code in gold_codes if code in ranked_codes)
        added = int(stats.get("union_added_n") or 0)
        added_counts.append(added)
        pool_sizes.append(len(ranked_codes))
        per_lesson[rid] = {
            "n_ranked": len(ranked_codes),
            "union_added_n": added,
            "pool_coverage": {
                "hits": pool_hits,
                "n": len(gold_codes),
                "rate": round(pool_hits / len(gold_codes), 4) if gold_codes else 0.0,
            },
            **lesson_metrics,
        }
        for code in gold_codes:
            n_pos += 1
            if code in ranked_codes:
                rank = ranked_codes.index(code) + 1
                rr_sum += 1.0 / rank
                for cutoff in cutoffs:
                    if rank <= cutoff:
                        hit_counts[cutoff] += 1

    pool_cov_hits = sum(
        int((per_lesson[rid].get("pool_coverage") or {}).get("hits") or 0)
        for rid in per_lesson
        if "error" not in per_lesson[rid]
    )
    return {
        "missing_positives": missing,
        "pool_size": {
            "avg": round(sum(pool_sizes) / len(pool_sizes), 2) if pool_sizes else 0.0,
            "max": max(pool_sizes) if pool_sizes else 0,
            "avg_union_added": (
                round(sum(added_counts) / len(added_counts), 2) if added_counts else 0.0
            ),
            "max_union_added": max(added_counts) if added_counts else 0,
        },
        "aggregated": {
            "n_positives": n_pos,
            "mrr": round(rr_sum / n_pos, 4) if n_pos else 0.0,
            "pool_coverage": {
                "hits": pool_cov_hits,
                "n": n_pos,
                "rate": round(pool_cov_hits / n_pos, 4) if n_pos else 0.0,
            },
            "recall": {
                f"@{c}": {
                    "hits": hit_counts[c],
                    "n": n_pos,
                    "rate": round(hit_counts[c] / n_pos, 4) if n_pos else 0.0,
                }
                for c in cutoffs
            },
            "note_ranked_recall": (
                "Ranked Recall@k uses primary-score order with union-only docs "
                "appended after primary top_k, so @10/@50 ranked rates often match "
                "single; pool_coverage is the membership recovery metric."
            ),
        },
        "per_lesson": per_lesson,
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Offline merge-aggregation eval from diagnostics")
    p.add_argument("--gold", default="output/reports/gold_set_batch1.jsonl")
    p.add_argument("--diag-dir", default="output/reports/retrieve_diag")
    p.add_argument("--out", default="output/reports/merge_aggregation_eval.json")
    p.add_argument("--merge-top-k", type=int, default=200)
    args = p.parse_args(argv)

    gold_rows = _load_gold_pairs(args.gold)
    gold_by_lesson: dict[str, list[str]] = defaultdict(list)
    for row in gold_rows:
        rid = row["resource_id"]
        code = row["standard_code"]
        if code not in gold_by_lesson[rid]:
            gold_by_lesson[rid].append(code)

    diag_dir = Path(args.diag_dir)
    cutoffs = DEFAULT_CUTOFFS
    configs = _configs()
    per_config: dict[str, Any] = {}

    for cfg in configs:
        label = cfg["label"]
        per_lesson: dict[str, Any] = {}
        all_gold: list[str] = []
        all_ranks: list[list[str]] = []
        # Flatten eval across lessons by collecting per-positive ranks.
        hit_counts = {k: 0 for k in cutoffs}
        rr_sum = 0.0
        n_pos = 0
        missing = 0

        for rid, gold_codes in sorted(gold_by_lesson.items()):
            diag_path = diag_dir / f"{rid}.json"
            if not diag_path.is_file():
                missing += len(gold_codes)
                per_lesson[rid] = {"error": "missing_diag"}
                continue
            diag = json.loads(diag_path.read_text(encoding="utf-8"))
            ranked_lists, weights, sources = _lists_from_diag(diag)
            if not ranked_lists:
                missing += len(gold_codes)
                per_lesson[rid] = {"error": "empty_per_query"}
                continue
            scored, _ = aggregate_multi_arm_rrf(
                ranked_lists,
                k=int(cfg["k"]),
                weights=weights,
                sources=sources,
                aggregation=str(cfg["aggregation"]),
                top_arms=int(cfg["top_arms"]),
                log_dampen_base=float(cfg["log_dampen_base"]),
            )
            ranked_codes = [code for code, _s in scored[: int(args.merge_top_k)]]
            lesson_metrics = _recall_at(ranked_codes, gold_codes, cutoffs)
            per_lesson[rid] = {
                "n_ranked": len(ranked_codes),
                **lesson_metrics,
            }
            for code in gold_codes:
                n_pos += 1
                if code in ranked_codes:
                    rank = ranked_codes.index(code) + 1
                    rr_sum += 1.0 / rank
                    for k in cutoffs:
                        if rank <= k:
                            hit_counts[k] += 1

        per_config[label] = {
            "config": cfg,
            "missing_positives": missing,
            "aggregated": {
                "n_positives": n_pos,
                "mrr": round(rr_sum / n_pos, 4) if n_pos else 0.0,
                "recall": {
                    f"@{k}": {
                        "hits": hit_counts[k],
                        "n": n_pos,
                        "rate": round(hit_counts[k] / n_pos, 4) if n_pos else 0.0,
                    }
                    for k in cutoffs
                },
            },
            "per_lesson": per_lesson,
        }

    # Highlight default-like configs for quick reading.
    highlight_labels = [
        "sum_k60",
        "max_k60",
        "top_k_sum_k60_n1",
        "top_k_sum_k60_n2",
        "top_k_sum_k60_n3",
        "log_dampened_k60_b2",
    ]
    summary = {
        label: per_config[label]["aggregated"]["recall"]
        for label in highlight_labels
        if label in per_config
    }

    # Primary follow-up: top_k_sum ordering + optional sum-side pool union.
    pool_compare = {
        "single": _eval_one_pool(
            gold_by_lesson=gold_by_lesson,
            diag_dir=diag_dir,
            merge_top_k=int(args.merge_top_k),
            cutoffs=cutoffs,
            aggregation="top_k_sum",
            top_arms=2,
            k=60,
            pool_membership_mode="single",
        ),
        "union": _eval_one_pool(
            gold_by_lesson=gold_by_lesson,
            diag_dir=diag_dir,
            merge_top_k=int(args.merge_top_k),
            cutoffs=cutoffs,
            aggregation="top_k_sum",
            top_arms=2,
            k=60,
            pool_membership_mode="union",
        ),
    }

    out = {
        "gold_source": str(args.gold),
        "diag_dir": str(args.diag_dir),
        "merge_top_k": int(args.merge_top_k),
        "note": (
            "Recomputes merge from cached per_query.hybrid_codes only. "
            "Does not include live sum-mode query_hit_weight extras. "
            "Gold used only as read-only eval metric."
        ),
        "query_arm_weight_flag": (
            "Per-arm weights still multiply each contribution "
            "(score += w/(k+rank)). Under sum this amplifies breadth when many "
            "medium-weight arms fire; max/top_k_sum/log_dampened reduce that "
            "mechanical breadth gain but weights still matter for which arms win."
        ),
        "frozen_grid": {
            "k": list(DEFAULT_K_GRID),
            "top_arms": list(DEFAULT_TOP_ARMS_GRID),
            "aggregations": list(MERGE_AGGREGATIONS),
            "log_dampen_base": 2.0,
        },
        "summary_k60": summary,
        "pool_membership_compare_top_k_sum_n2_k60": {
            "note": (
                "Ordering always top_k_sum(n=2). "
                "union membership = top merge_top_k(primary) ∪ top merge_top_k(sum)."
            ),
            "single": pool_compare["single"],
            "union": pool_compare["union"],
            "checks": {
                "recall_at10_unchanged_or_better": (
                    pool_compare["union"]["aggregated"]["recall"]["@10"]["rate"]
                    >= pool_compare["single"]["aggregated"]["recall"]["@10"]["rate"]
                ),
                "pool_coverage_improved": (
                    pool_compare["union"]["aggregated"]["pool_coverage"]["rate"]
                    >= pool_compare["single"]["aggregated"]["pool_coverage"]["rate"]
                ),
            },
        },
        "results": per_config,
    }
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "wrote": str(out_path),
                "summary_k60": summary,
                "pool_membership_compare": {
                    mode: {
                        "recall": pool_compare[mode]["aggregated"]["recall"],
                        "pool_coverage": pool_compare[mode]["aggregated"]["pool_coverage"],
                        "pool_size": pool_compare[mode]["pool_size"],
                    }
                    for mode in ("single", "union")
                },
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
