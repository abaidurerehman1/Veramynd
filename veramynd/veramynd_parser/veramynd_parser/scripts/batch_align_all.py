"""Batch retrieve + judge for all Stage-1 lessons in a unit, then report.

Example:
  python -m veramynd_parser.scripts.batch_align_all \\
    --lessons-dir output/stage1/lessons \\
    --chunks-dir output/chunks/by_lesson \\
    --standards-dir output/normalize_standards
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

# Allow running as ``python scripts/batch_align_all.py`` from package root.
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT.parent))

from veramynd_parser.judge.pipeline import (
    JudgeError,
    JudgeIncompleteError,
    judge_retrieve_file,
    write_judge_report,
)
from veramynd_parser.normalize.llm import LlmError, is_non_retryable_openai_error
from veramynd_parser.report.dashboard import write_html_dashboard
from veramynd_parser.report.exporter import export_alignment_report
from veramynd_parser.retrieve.diagnostics import (
    build_diagnostics_payload,
    write_diagnostics,
)
from veramynd_parser.retrieve.gold_metrics import (
    report_leaf_recall,
    resource_ids_from_gold,
)
from veramynd_parser.retrieve.io import (
    instructional_queries_from_chunk_bundle,
    lesson_query_from_chunk_bundle,
    rerank_query_from_chunk_bundle,
)
from veramynd_parser.retrieve.pipeline import (
    DEFAULT_ARM_LIMIT,
    DEFAULT_EXHAUSTIVE_CEILING,
    DEFAULT_JUDGE_SHORTLIST_K,
    DEFAULT_MERGE_AGGREGATION,
    DEFAULT_MERGE_LOG_DAMPEN_BASE,
    DEFAULT_MERGE_MAX_BLEND,
    DEFAULT_MERGE_TOP_ARMS,
    DEFAULT_MERGE_TOP_K,
    DEFAULT_PER_QUERY_TOP_K,
    DEFAULT_PARENT_CAP,
    DEFAULT_POOL_MEMBERSHIP_MODE,
    DEFAULT_HYBRID_TOP_K,
    DEFAULT_PRESERVE_RRF_TOP,
    DEFAULT_RERANK_BLEND_RRF,
    DEFAULT_RERANK_TOP_N,
    DEFAULT_RERANK_TOP_N_ENTERPRISE,
    DEFAULT_SHORTLIST_CE_WEIGHT,
    DEFAULT_SHORTLIST_RRF_WEIGHT,
    DEFAULT_SHORTLIST_RESCUE_SLOTS,
    DEFAULT_SHORTLIST_SKILL_WEIGHT,
    DEFAULT_SHORTLIST_DOMAIN_WEIGHT,
    DEFAULT_SHORTLIST_HIT_WEIGHT,
    DEFAULT_SHORTLIST_ARM_WEIGHT,
    DEFAULT_SHORTLIST_MID_CE_BOOST,
    DEFAULT_SHORTLIST_MID_CE_MAX,
    DEFAULT_SHORTLIST_MID_RRF_MAX,
    DEFAULT_SHORTLIST_MID_RRF_MIN,
    DEFAULT_SHORTLIST_RRF_HEAD_LOCK,
    RetrieveError,
    build_judge_shortlist,
    multi_query_retrieve_and_rerank,
    retrieve_and_rerank,
)
from veramynd_parser.retrieve.rrf import MERGE_AGGREGATIONS, POOL_MEMBERSHIP_MODES
from veramynd_parser.retrieve.queries import (
    domains_from_normalize,
    focused_queries_from_normalize,
    grade_from_normalize,
    query_arm_weight,
    query_counts_for_coverage,
    rerank_context_from_normalize,
    skill_focus_text_from_normalize,
)
from veramynd_parser.text_utils import atomic_write_text


def _lesson_ids(lessons_dir: Path) -> list[str]:
    return sorted(p.stem for p in lessons_dir.glob("*.json"))


def _gold_codes_by_lesson(gold_jsonl: Path) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for line in gold_jsonl.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        row = json.loads(line)
        status = (row.get("matched_status") or "").strip().lower()
        if status not in {"full", "partial"}:
            continue
        rid = (row.get("resource_id") or "").strip()
        code = (row.get("standard_code") or "").strip()
        if not rid or not code:
            continue
        out.setdefault(rid, [])
        if code not in out[rid]:
            out[rid].append(code)
    return out


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Batch retrieve+judge+report for all lessons")
    p.add_argument("--lessons-dir", default="output/stage1/lessons")
    p.add_argument("--chunks-dir", default="output/chunks/by_lesson")
    p.add_argument("--normalize-dir", default="output/normalize")
    p.add_argument("--standards-dir", default="output/normalize_standards")
    p.add_argument("--retrieve-dir", default="output/retrieve")
    p.add_argument("--judge-dir", default="output/judge")
    p.add_argument("--report-csv", default="output/reports/alignments_all.csv")
    p.add_argument("--skip-retrieve", action="store_true")
    p.add_argument("--skip-judge", action="store_true")
    p.add_argument("--skip-report", action="store_true")
    p.add_argument("--no-rerank", action="store_true")
    p.add_argument(
        "--escalate",
        action="store_true",
        help="deprecated: escalate is ON by default",
    )
    p.add_argument(
        "--no-escalate",
        action="store_true",
        help="disable enterprise escalate cascade (cheaper smoke runs)",
    )
    p.add_argument(
        "--force",
        action="store_true",
        help="maintenance: force retrieve + judge (and bypass judge LLM cache)",
    )
    p.add_argument(
        "--force-retrieve",
        action="store_true",
        help="re-run retrieve even if output JSON already exists",
    )
    p.add_argument(
        "--force-judge",
        action="store_true",
        help="re-run judge even if output JSON already exists (also bypasses judge cache)",
    )
    p.add_argument(
        "--no-cache",
        action="store_true",
        help="disable judge LLM cache reads/writes",
    )
    judge_mode = p.add_mutually_exclusive_group()
    judge_mode.add_argument(
        "--batch",
        action="store_true",
        help="opt into one judge call per lesson (cheaper, lower pair depth)",
    )
    judge_mode.add_argument(
        "--no-batch",
        action="store_true",
        help="deprecated: pair-depth judging is already the default",
    )
    p.add_argument(
        "--use-batch-api",
        action="store_true",
        help=(
            "execute each lesson's judge call(s) through Anthropic's async "
            "Message Batches API (flat 50%% off, stacks with prompt caching); "
            "blocks per lesson until that lesson's batch job ends"
        ),
    )
    p.add_argument(
        "--self-consistency-n",
        type=int,
        default=1,
        help=(
            "sample escalated (hard/borderline) verdicts N times at nonzero "
            "temperature and majority-vote instead of one deterministic "
            "escalate call (default 1 = off)"
        ),
    )
    p.add_argument(
        "--prescreen-min-rerank-score",
        type=float,
        default=None,
        help=(
            "Tier-1 cost lever: candidates with retrieval rerank_score below "
            "this value are judged 'none' with no LLM call (default: off). "
            "NOT calibrated automatically — verify against the gold set "
            "before using this in production."
        ),
    )
    p.add_argument("--limit-lessons", type=int, default=None)
    p.add_argument("--only", action="append", default=[], help="limit to resource id(s)")
    retrieve_mode = p.add_mutually_exclusive_group()
    retrieve_mode.add_argument(
        "--multi-query",
        dest="multi_query",
        action="store_true",
        default=True,
        help="enterprise multi-query retrieve (default)",
    )
    retrieve_mode.add_argument(
        "--single-query",
        dest="multi_query",
        action="store_false",
        help="legacy single lesson-blob retrieval (disables stage diagnostics)",
    )
    p.add_argument(
        "--from-gold",
        default=None,
        help="limit retrieve to resource_ids listed in this gold JSONL (no hard-coded IDs)",
    )
    p.add_argument(
        "--diag-dir",
        default="output/reports/retrieve_diag",
        help="write per-lesson multi-query retrieval diagnostics",
    )
    p.add_argument("--arm-limit", type=int, default=DEFAULT_ARM_LIMIT)
    p.add_argument("--merge-top-k", type=int, default=DEFAULT_MERGE_TOP_K)
    p.add_argument("--per-query-top-k", type=int, default=DEFAULT_PER_QUERY_TOP_K)
    p.add_argument("--rerank-k", type=int, default=DEFAULT_RERANK_TOP_N_ENTERPRISE)
    p.add_argument(
        "--exhaustive-ceiling",
        type=int,
        default=DEFAULT_EXHAUSTIVE_CEILING,
        help="score all grade leaves locally when corpus size is at or below this limit",
    )
    p.add_argument("--blend-rrf", type=float, default=DEFAULT_RERANK_BLEND_RRF)
    p.add_argument("--preserve-rrf-top", type=int, default=DEFAULT_PRESERVE_RRF_TOP)
    p.add_argument(
        "--judge-shortlist-k",
        type=int,
        default=DEFAULT_JUDGE_SHORTLIST_K,
        help="cost-aware final candidates[] size sent to judge",
    )
    p.add_argument(
        "--shortlist-rrf-weight",
        type=float,
        default=DEFAULT_SHORTLIST_RRF_WEIGHT,
        help="first-stage RRF weight in rerank+RRF shortlist fusion",
    )
    p.add_argument(
        "--parent-cap",
        type=int,
        default=DEFAULT_PARENT_CAP,
        help="maximum siblings from one standard parent in the GPT shortlist",
    )
    p.add_argument(
        "--merge-aggregation",
        choices=list(MERGE_AGGREGATIONS),
        default=DEFAULT_MERGE_AGGREGATION,
        help="multi-query merge aggregation: sum (default) | max | top_k_sum | log_dampened",
    )
    p.add_argument(
        "--merge-top-arms",
        type=int,
        default=DEFAULT_MERGE_TOP_ARMS,
        help="for top_k_sum: how many strongest arms to keep",
    )
    p.add_argument(
        "--merge-log-dampen-base",
        type=float,
        default=DEFAULT_MERGE_LOG_DAMPEN_BASE,
        help="for log_dampened: log base (>1) in log_b(1+n_hits)/n_hits",
    )
    p.add_argument(
        "--pool-membership-mode",
        choices=list(POOL_MEMBERSHIP_MODES),
        default=DEFAULT_POOL_MEMBERSHIP_MODE,
        help="single=top by primary aggregation; union=primary top ∪ sum top",
    )
    p.add_argument(
        "--shortlist-rescue-slots",
        type=int,
        default=DEFAULT_SHORTLIST_RESCUE_SLOTS,
        help=(
            "reserve N final shortlist slots for classic-sum rescue "
            "(0=default fused top_n only; core=top_n-N unchanged)"
        ),
    )
    args = p.parse_args(argv)

    if args.force:
        args.force_retrieve = True
        args.force_judge = True
        args.no_cache = True

    lessons_dir = Path(args.lessons_dir)
    chunks_dir = Path(args.chunks_dir)
    normalize_dir = Path(args.normalize_dir)
    standards_dir = Path(args.standards_dir)
    retrieve_dir = Path(args.retrieve_dir)
    judge_dir = Path(args.judge_dir)
    diag_dir = Path(args.diag_dir)
    retrieve_dir.mkdir(parents=True, exist_ok=True)
    judge_dir.mkdir(parents=True, exist_ok=True)

    ids = _lesson_ids(lessons_dir)
    gold_by_lesson: dict[str, list[str]] = {}
    if args.from_gold:
        gold_path = Path(args.from_gold)
        if not gold_path.is_file():
            print(f"ERROR: gold file not found: {gold_path}", file=sys.stderr)
            return 2
        want_gold = set(resource_ids_from_gold(gold_path))
        ids = [i for i in ids if i in want_gold]
        gold_by_lesson = _gold_codes_by_lesson(gold_path)
    if args.only:
        want = set(args.only)
        ids = [i for i in ids if i in want]
    if args.limit_lessons is not None:
        if args.limit_lessons < 0:
            print(
                f"ERROR: --limit-lessons must be >= 0, got {args.limit_lessons}",
                file=sys.stderr,
            )
            return 2
        # 0 means "zero lessons" (an explicit smoke no-op), not "no limit".
        ids = ids[: args.limit_lessons]
    if not ids:
        print("ERROR: no lessons found", file=sys.stderr)
        return 2

    print(f"Batch aligning {len(ids)} lessons...", flush=True)
    t0 = time.time()
    failed: list[dict[str, str]] = []

    # Load BM25/docs once via first retrieve (process cache), and keep reranker warm.
    if not args.skip_retrieve:
        for i, rid in enumerate(ids, start=1):
            chunk = chunks_dir / f"{rid}.json"
            out = retrieve_dir / f"{rid}.json"
            if not chunk.is_file() and not args.multi_query:
                failed.append({"resource_id": rid, "stage": "retrieve", "error": "missing chunk"})
                print(f"[{i}/{len(ids)}] SKIP retrieve {rid}: missing chunk", flush=True)
                continue
            if out.is_file() and not args.force_retrieve:
                print(f"[{i}/{len(ids)}] SKIP retrieve {rid}: already exists", flush=True)
                continue
            print(f"[{i}/{len(ids)}] retrieve {rid}...", flush=True)
            try:
                if args.multi_query:
                    norm = normalize_dir / f"{rid}.json"
                    query_meta: list[dict[str, str]] = []
                    lesson_grade: int | None = None
                    if norm.is_file():
                        query_meta = focused_queries_from_normalize(norm)
                        rerank_q = rerank_context_from_normalize(norm)
                        lesson_grade = grade_from_normalize(norm)
                        lesson_domains = domains_from_normalize(norm)
                        lesson_skill_focus = skill_focus_text_from_normalize(norm)
                        query_mode = "multi_normalize_focused"
                    else:
                        # Fallback: instructional chunks (still multi-query).
                        qpairs = instructional_queries_from_chunk_bundle(chunk)
                        query_meta = [
                            {
                                "query_id": label,
                                "source": "instructional_chunk",
                                "text": text,
                            }
                            for text, label in qpairs
                        ]
                        rerank_q = rerank_query_from_chunk_bundle(chunk)
                        lesson_domains = []
                        lesson_skill_focus = ""
                        query_mode = "multi_instructional_fallback"
                    queries = [q["text"] for q in query_meta]
                    sources = [q["query_id"] for q in query_meta]
                    arm_weights = [
                        query_arm_weight(str(q.get("source") or "")) for q in query_meta
                    ]
                    coverage_mask = [
                        query_counts_for_coverage(str(q.get("source") or ""))
                        for q in query_meta
                    ]
                    query_sources = [str(q.get("source") or "") for q in query_meta]
                    hits, rrf_hits, per_q = multi_query_retrieve_and_rerank(
                        queries,
                        standards_dir,
                        rerank_query=rerank_q,
                        per_query_top_k=int(args.per_query_top_k),
                        merge_top_k=int(args.merge_top_k),
                        arm_limit=int(args.arm_limit),
                        rerank_k=int(args.rerank_k),
                        skip_rerank=bool(args.no_rerank),
                        blend_rrf=float(args.blend_rrf),
                        preserve_rrf_top=int(args.preserve_rrf_top),
                        exhaustive_ceiling=int(args.exhaustive_ceiling),
                        collect_diagnostics=True,
                        grade=lesson_grade,
                        query_weights=arm_weights,
                        query_coverage_mask=coverage_mask,
                        query_sources=query_sources,
                        merge_aggregation=str(args.merge_aggregation),
                        merge_top_arms=int(args.merge_top_arms),
                        merge_log_dampen_base=float(args.merge_log_dampen_base),
                        merge_max_blend=float(DEFAULT_MERGE_MAX_BLEND),
                        pool_membership_mode=str(args.pool_membership_mode),
                    )
                    shortlist = build_judge_shortlist(
                        hits,
                        rrf_hits,
                        top_n=int(args.judge_shortlist_k),
                        ce_weight=DEFAULT_SHORTLIST_CE_WEIGHT,
                        rrf_weight=float(args.shortlist_rrf_weight),
                        parent_cap=int(args.parent_cap),
                        lesson_domains=lesson_domains,
                        lesson_skill_focus=lesson_skill_focus,
                        rescue_slots=int(args.shortlist_rescue_slots),
                        skill_weight=DEFAULT_SHORTLIST_SKILL_WEIGHT,
                        domain_weight=DEFAULT_SHORTLIST_DOMAIN_WEIGHT,
                        hit_weight=DEFAULT_SHORTLIST_HIT_WEIGHT,
                        arm_weight=DEFAULT_SHORTLIST_ARM_WEIGHT,
                    )
                    # Attach query metadata onto diagnostics rows.
                    for row, meta in zip(per_q, query_meta):
                        row["query_id"] = meta.get("query_id")
                        row["source"] = meta.get("source")
                        row["text_preview"] = (meta.get("text") or "")[:240]
                    payload = {
                        "schema_version": "1.2-retrieve-enterprise",
                        "query_mode": query_mode,
                        "query_source": ";".join(sources),
                        "query_sources": sources,
                        "n_queries": len(queries),
                        "grade_filter": lesson_grade,
                        "arm_limit": int(args.arm_limit),
                        "per_query_top_k": int(args.per_query_top_k),
                        "merge_top_k": int(args.merge_top_k),
                        "rerank_k": int(args.rerank_k),
                        "exhaustive_ceiling": int(args.exhaustive_ceiling),
                        "blend_rrf": float(args.blend_rrf),
                        "preserve_rrf_top": int(args.preserve_rrf_top),
                        "judge_shortlist_k": int(args.judge_shortlist_k),
                        "shortlist_rrf_weight": float(args.shortlist_rrf_weight),
                        "shortlist_ce_weight": DEFAULT_SHORTLIST_CE_WEIGHT,
                        "shortlist_rescue_slots": int(args.shortlist_rescue_slots),
                        "shortlist_skill_weight": DEFAULT_SHORTLIST_SKILL_WEIGHT,
                        "shortlist_domain_weight": DEFAULT_SHORTLIST_DOMAIN_WEIGHT,
                        "shortlist_hit_weight": DEFAULT_SHORTLIST_HIT_WEIGHT,
                        "shortlist_arm_weight": DEFAULT_SHORTLIST_ARM_WEIGHT,
                        "parent_cap": int(args.parent_cap),
                        "merge_aggregation": str(args.merge_aggregation),
                        "merge_top_arms": int(args.merge_top_arms),
                        "merge_log_dampen_base": float(args.merge_log_dampen_base),
                        "merge_max_blend": float(DEFAULT_MERGE_MAX_BLEND),
                        "pool_membership_mode": str(args.pool_membership_mode),
                        "shortlist_mid_ce_boost": float(DEFAULT_SHORTLIST_MID_CE_BOOST),
                        "shortlist_mid_rrf_min": int(DEFAULT_SHORTLIST_MID_RRF_MIN),
                        "shortlist_mid_rrf_max": int(DEFAULT_SHORTLIST_MID_RRF_MAX),
                        "shortlist_mid_ce_max": int(DEFAULT_SHORTLIST_MID_CE_MAX),
                        "shortlist_rrf_head_lock": int(DEFAULT_SHORTLIST_RRF_HEAD_LOCK),
                        "skip_rerank": bool(args.no_rerank),
                        "candidate_count": len(shortlist),
                        "candidates": [
                            {
                                k: v
                                for k, v in c.to_dict().items()
                                if k not in {"text", "arm_hits"}
                            }
                            for c in shortlist
                        ],
                    }
                    atomic_write_text(out, json.dumps(payload, indent=2) + "\n")
                    diag = build_diagnostics_payload(
                        resource_id=rid,
                        queries=query_meta,
                        per_query=per_q,
                        merged=rrf_hits,
                        reranked=hits,
                        shortlist=shortlist,
                        # Evaluation-only annotation written after ranking.
                        # Gold codes never enter query generation, fusion,
                        # reranking, diversity, or candidate selection.
                        gold_codes=gold_by_lesson.get(rid),
                        extra={
                            "query_mode": query_mode,
                            "arm_limit": int(args.arm_limit),
                            "merge_top_k": int(args.merge_top_k),
                            "rerank_k": int(args.rerank_k),
                            "exhaustive_ceiling": int(args.exhaustive_ceiling),
                            "judge_shortlist_k": int(args.judge_shortlist_k),
                            "shortlist_rescue_slots": int(args.shortlist_rescue_slots),
                            "parent_cap": int(args.parent_cap),
                        },
                    )
                    write_diagnostics(diag_dir / f"{rid}.json", diag)
                else:
                    if not chunk.is_file():
                        raise FileNotFoundError(f"missing chunk: {chunk}")
                    query, source = lesson_query_from_chunk_bundle(
                        chunk, family="lesson"
                    )
                    hits = retrieve_and_rerank(
                        query,
                        standards_dir,
                        skip_rerank=bool(args.no_rerank),
                    )
                    payload = {
                        "schema_version": "1.0-retrieve-hybrid",
                        "query_mode": "lesson",
                        "query_source": source,
                        # Record the defaults retrieve_and_rerank actually used.
                        "top_k": DEFAULT_HYBRID_TOP_K,
                        "rerank_k": DEFAULT_RERANK_TOP_N,
                        "skip_rerank": bool(args.no_rerank),
                        "candidates": [c.to_dict() for c in hits],
                    }
                    atomic_write_text(out, json.dumps(payload, indent=2) + "\n")
            except (RetrieveError, OSError, ValueError, RuntimeError) as e:
                failed.append({"resource_id": rid, "stage": "retrieve", "error": str(e)})
                print(f"  ERROR retrieve {rid}: {e}", flush=True)

        if args.from_gold and args.multi_query:
            metrics = report_leaf_recall(Path(args.from_gold), retrieve_dir)
            metrics_path = Path("output/reports/retrieve_gold_metrics.json")
            metrics_path.parent.mkdir(parents=True, exist_ok=True)
            atomic_write_text(metrics_path, json.dumps(metrics, indent=2) + "\n")
            print(
                "Gold leaf recall (retrieve-side report, eval pipeline untouched):",
                flush=True,
            )
            print(json.dumps(metrics, indent=2), flush=True)

    if not args.skip_judge:
        for i, rid in enumerate(ids, start=1):
            retrieve_file = retrieve_dir / f"{rid}.json"
            lesson_file = lessons_dir / f"{rid}.json"
            out = judge_dir / f"{rid}.json"
            if not retrieve_file.is_file():
                failed.append({"resource_id": rid, "stage": "judge", "error": "missing retrieve"})
                print(f"[{i}/{len(ids)}] SKIP judge {rid}: missing retrieve", flush=True)
                continue
            if not lesson_file.is_file():
                failed.append({"resource_id": rid, "stage": "judge", "error": "missing lesson"})
                print(f"[{i}/{len(ids)}] SKIP judge {rid}: missing lesson", flush=True)
                continue
            if out.is_file() and not args.force_judge:
                print(f"[{i}/{len(ids)}] SKIP judge {rid}: already exists", flush=True)
                continue
            print(f"[{i}/{len(ids)}] judge {rid}...", flush=True)
            try:
                report = judge_retrieve_file(
                    retrieve_file=retrieve_file,
                    standards_dir=standards_dir,
                    lesson_file=lesson_file,
                    escalate=not bool(args.no_escalate),
                    batch=bool(args.batch),
                    use_cache=not (
                        bool(args.no_cache) or bool(args.force_judge) or bool(args.force)
                    ),
                    use_batch_api=bool(args.use_batch_api),
                    self_consistency_n=int(args.self_consistency_n),
                    prescreen_min_rerank_score=args.prescreen_min_rerank_score,
                )
                write_judge_report(report, out)
                by = report.get("by_status") or {}
                print(
                    f"  ok full={by.get('full', 0)} partial={by.get('partial', 0)} "
                    f"none={by.get('none', 0)} grounding={report.get('grounding_rate')}",
                    flush=True,
                )
            except JudgeIncompleteError as e:
                incomplete = Path(str(out) + ".incomplete.json")
                write_judge_report(e.report, incomplete)
                failed.append({"resource_id": rid, "stage": "judge", "error": str(e)})
                print(f"  INCOMPLETE {rid}: {e}", flush=True)
            except (JudgeError, LlmError, OSError, ValueError, RuntimeError) as e:
                failed.append({"resource_id": rid, "stage": "judge", "error": str(e)})
                print(f"  ERROR judge {rid}: {e}", flush=True)
                if is_non_retryable_openai_error(e):
                    remaining = len(ids) - i
                    print(
                        "ABORT: non-retryable OpenAI error "
                        f"(billing/quota) — skipping {remaining} remaining lesson(s).",
                        flush=True,
                    )
                    break

    if not args.skip_report:
        judge_files = sorted(judge_dir.glob("*.json"))
        judge_files = [f for f in judge_files if not f.name.endswith(".incomplete.json")]
        if not judge_files:
            print("WARN: no judge JSON files — skipping report", flush=True)
        else:
            print(f"Report from {len(judge_files)} judge files...", flush=True)
            summary = export_alignment_report(
                judge_files,
                out_csv=args.report_csv,
                include_none=True,
            )
            html = write_html_dashboard(
                judge_files,
                Path(args.report_csv).with_suffix(".html"),
                include_none=True,
            )
            print(f"Wrote {summary.get('csv_path')}", flush=True)
            print(f"Wrote {summary.get('summary_path')}", flush=True)
            print(f"Wrote {html}", flush=True)

    manifest = {
        "lessons": ids,
        "failed": failed,
        "elapsed_sec": round(time.time() - t0, 1),
        "ok_count": len(ids) - len({f["resource_id"] for f in failed}),
    }
    man_path = Path(args.report_csv).parent / "batch_align_manifest.json"
    man_path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(man_path, json.dumps(manifest, indent=2) + "\n")
    print(
        f"Done. lessons={len(ids)} failed={len(failed)} "
        f"elapsed={manifest['elapsed_sec']}s -> {man_path}",
        flush=True,
    )
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
