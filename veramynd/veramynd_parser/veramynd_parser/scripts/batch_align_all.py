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
from veramynd_parser.normalize.llm import LlmError
from veramynd_parser.report.dashboard import write_html_dashboard
from veramynd_parser.report.exporter import export_alignment_report
from veramynd_parser.retrieve.io import lesson_query_from_chunk_bundle
from veramynd_parser.retrieve.pipeline import RetrieveError, retrieve_and_rerank
from veramynd_parser.text_utils import atomic_write_text


def _lesson_ids(lessons_dir: Path) -> list[str]:
    return sorted(p.stem for p in lessons_dir.glob("*.json"))


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Batch retrieve+judge+report for all lessons")
    p.add_argument("--lessons-dir", default="output/stage1/lessons")
    p.add_argument("--chunks-dir", default="output/chunks/by_lesson")
    p.add_argument("--standards-dir", default="output/normalize_standards")
    p.add_argument("--retrieve-dir", default="output/retrieve")
    p.add_argument("--judge-dir", default="output/judge")
    p.add_argument("--report-csv", default="output/reports/alignments_all.csv")
    p.add_argument("--skip-retrieve", action="store_true")
    p.add_argument("--skip-judge", action="store_true")
    p.add_argument("--skip-report", action="store_true")
    p.add_argument("--no-rerank", action="store_true")
    p.add_argument("--escalate", action="store_true")
    p.add_argument(
        "--force-retrieve",
        action="store_true",
        help="re-run retrieve even if output JSON already exists",
    )
    p.add_argument(
        "--force-judge",
        action="store_true",
        help="re-run judge even if output JSON already exists",
    )
    p.add_argument(
        "--no-batch",
        action="store_true",
        help="per-candidate judge calls instead of one call per lesson",
    )
    p.add_argument("--limit-lessons", type=int, default=None)
    p.add_argument("--only", action="append", default=[], help="limit to resource id(s)")
    args = p.parse_args(argv)

    lessons_dir = Path(args.lessons_dir)
    chunks_dir = Path(args.chunks_dir)
    standards_dir = Path(args.standards_dir)
    retrieve_dir = Path(args.retrieve_dir)
    judge_dir = Path(args.judge_dir)
    retrieve_dir.mkdir(parents=True, exist_ok=True)
    judge_dir.mkdir(parents=True, exist_ok=True)

    ids = _lesson_ids(lessons_dir)
    if args.only:
        want = set(args.only)
        ids = [i for i in ids if i in want]
    if args.limit_lessons:
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
            if not chunk.is_file():
                failed.append({"resource_id": rid, "stage": "retrieve", "error": "missing chunk"})
                print(f"[{i}/{len(ids)}] SKIP retrieve {rid}: missing chunk", flush=True)
                continue
            if out.is_file() and not args.force_retrieve:
                print(f"[{i}/{len(ids)}] SKIP retrieve {rid}: already exists", flush=True)
                continue
            print(f"[{i}/{len(ids)}] retrieve {rid}...", flush=True)
            try:
                query, source = lesson_query_from_chunk_bundle(chunk, family="lesson")
                hits = retrieve_and_rerank(
                    query,
                    standards_dir,
                    skip_rerank=bool(args.no_rerank),
                )
                payload = {
                    "schema_version": "1.0-retrieve-hybrid",
                    "query_source": source,
                    "top_k": 30,
                    "rerank_k": 10,
                    "skip_rerank": bool(args.no_rerank),
                    "candidates": [c.to_dict() for c in hits],
                }
                atomic_write_text(out, json.dumps(payload, indent=2) + "\n")
            except (RetrieveError, OSError, ValueError, RuntimeError) as e:
                failed.append({"resource_id": rid, "stage": "retrieve", "error": str(e)})
                print(f"  ERROR retrieve {rid}: {e}", flush=True)

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
                    escalate=bool(args.escalate),
                    batch=not bool(args.no_batch),
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

    if not args.skip_report:
        judge_files = sorted(judge_dir.glob("G*.json"))
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
