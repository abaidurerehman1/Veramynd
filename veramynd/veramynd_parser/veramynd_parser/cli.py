"""Command-line interface.

    python -m veramynd_parser.cli guide  <teacher_guide.pdf>  [--json out.json]
    python -m veramynd_parser.cli stds   <standards.xlsx>     [--json out.json]
    python -m veramynd_parser.cli verify <teacher_guide.pdf>  [--expect 40]
    python -m veramynd_parser.cli export <teacher_guide.pdf>  [--out output/stage1 --standards x.xlsx]
    python -m veramynd_parser.cli normalize-lessons <lessons_dir> [--out DIR]

Parse commands accept ``--engine docling|pymupdf`` and ``--ocr auto|on|off``.
``verify`` runs the safety net and exits non-zero if any hard check FAILs (a CI gate);
``export`` writes every detected lesson (plus the verification report) to a folder --
on a BLOCK verdict, the trusted per-lesson output is withheld by default (only the
report is written) unless ``--allow-block`` is passed. On GO, the report is written
only together with the trusted artifacts so a mid-export failure cannot leave a
fresh GO report beside a stale ``lessons/`` tree.
``normalize-lessons`` runs the ELA curriculum normalizer (OpenAI only; resumable, cached).
``normalize-standards`` normalizes Stage-1 standards.json leaves into retrieval records.
``chunk-lessons`` builds production hierarchical chunks (lesson + instructional + evidence pointers).
``embed-chunks`` embeds lesson/instructional chunks with OpenAI text-embedding-3-large into Qdrant.
``embed-standards`` embeds normalized standard leaves into Qdrant collection veramynd_standards.
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

from .chunk.builder import chunk_lessons_dir
from .config import Config, NormalizeConfig
from .embed.runner import (
    DEFAULT_COLLECTION,
    DEFAULT_DIMENSIONS,
    DEFAULT_EMBEDDING_MODEL,
    DEFAULT_STANDARDS_COLLECTION,
    EmbedError,
    embed_chunks_to_qdrant,
    embed_standards_to_qdrant,
    query_standards_by_text,
)
from .normalize.lesson import normalize_lesson, normalize_lessons_dir, repair_normalized_dir
from .normalize.llm import LlmError
from .normalize.models import dump_ela_record_json
from .normalize.standard import normalize_standard, normalize_standards_tree
from .normalize.standard_models import dump_normalized_standard_json
from .models import GradeStandards, Standard, StandardLevel
from .pdf.document import PdfDocument
from .pdf.teacher_guide import parse_teacher_guide
from .standards.spreadsheet import SpreadsheetStructureError, parse_standards
from .text_utils import atomic_replace_dir, atomic_write_text, safe_code_filename
from .verify.verifier import verify


def _config(args: argparse.Namespace) -> Config:
    """Build a Config from common CLI flags (--engine, --ocr, --cross-engine)."""
    return Config(
        engine=getattr(args, "engine", "docling"),
        ocr_mode=getattr(args, "ocr", "auto"),
        export_printed_pages=not getattr(args, "pdf_pages", False),
        cross_engine_structural_check=getattr(args, "cross_engine", False),
    )


def _guide_for_json_export(guide, pdf_path: str, cfg: Config):
    """Remap page fields to printed footers for JSON export (default).

    Raises ``PageMapError`` on failure so callers can avoid writing a fresh GO
    report before the remap succeeds.
    """
    if not cfg.export_printed_pages:
        return guide
    from .pdf.export_pages import for_export

    return for_export(guide, pdf_path)


def _normalize_config(args: argparse.Namespace) -> Config:
    from .normalize.llm import load_dotenv

    load_dotenv()
    defaults = Config()
    return Config(
        normalize=NormalizeConfig(
            model=getattr(args, "model", None) or "",
            cache_dir=getattr(args, "cache_dir", None) or defaults.normalize.cache_dir,
            max_tokens=getattr(args, "max_tokens", None),
        ),
    )


def _add_parse_flags(p: argparse.ArgumentParser) -> None:
    p.add_argument(
        "--engine",
        choices=["docling", "pymupdf"],
        default="docling",
        help="content engine (default: docling)",
    )
    p.add_argument(
        "--ocr",
        choices=["auto", "on", "off"],
        default="auto",
        help="OCR policy for Docling (default: auto -- detect text layer)",
    )
    p.add_argument(
        "--pdf-pages",
        action="store_true",
        help="keep PDF page indices in exported JSON (default: remap to printed footers)",
    )
    p.add_argument(
        "--cross-engine",
        action="store_true",
        help=(
            "also independently re-divide every lesson with PyMuPDF and require full "
            "structural agreement with the Docling parse (verifier check V15). Off by "
            "default -- a second full parse, not a cheap check; turn on for a nightly "
            "re-verify or before trusting a new document."
        ),
    )


def _print_guide_summary(guide) -> None:
    n_tables = sum(len(l.tables) for l in guide.lessons)
    ocr = "on" if guide.ocr_used else "off (text layer)"
    print(f"Source     : {guide.source_id}")
    print(f"Engine     : {guide.engine} (content)  |  pymupdf (outline + verify)")
    print(f"OCR        : {ocr}")
    if guide.separation_fallback_reason:
        print(f"WARNING    : separation fell back to font/header scan -- {guide.separation_fallback_reason}")
    if guide.engine_fallback_reason:
        print(f"WARNING    : content engine fell back to PyMuPDF -- {guide.engine_fallback_reason}")
    print(f"Grade/Mod  : {guide.grade} / {guide.module}")
    print(f"Pages      : {guide.page_count}")
    print(f"Units      : {len(guide.units)}")
    print(f"Lessons    : {len(guide.lessons)}")
    print(f"Tables     : {n_tables} (Docling)")
    for unit in guide.units:
        first, last = unit.lessons[0], unit.lessons[-1]
        print(
            f"  Unit {unit.unit}: {len(unit.lessons):>2} lessons "
            f"(pp. {first.page_start}-{last.page_end})"
        )


def cmd_guide(args: argparse.Namespace) -> int:
    from .pdf.page_map import PageMapError

    cfg = _config(args)
    guide = parse_teacher_guide(args.path, cfg)
    _print_guide_summary(guide)
    if args.json:
        try:
            exported = _guide_for_json_export(guide, args.path, cfg)
        except PageMapError as e:
            print(f"ERROR: printed page map failed: {e}", file=sys.stderr)
            return 1
        json_path = Path(args.json)
        json_path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_text(json_path, exported.model_dump_json(indent=2))
        print(f"\nwrote {args.json}")
        if cfg.export_printed_pages:
            print("(page numbers in JSON are printed footer pages, not PDF indices)")
    return 0


def cmd_standards(args: argparse.Namespace) -> int:
    stds = parse_standards(args.path)
    from .models import StandardLevel

    print(f"Source     : {args.path}")
    print(f"Grade      : {stds.grade}  Framework: {stds.framework}")
    print(f"Standards  : {len(stds.standards)}")
    for level in StandardLevel:
        print(f"  {level.value:<12}: {len(stds.by_level(level))}")
    if args.json:
        json_path = Path(args.json)
        json_path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_text(json_path, stds.model_dump_json(indent=2))
        print(f"\nwrote {args.json}")
    return 0


def cmd_export(args: argparse.Namespace) -> int:
    """Parse, verify, and write everything the parser detects to a folder.

    On a BLOCK verdict (any hard verification check FAILs), the trusted output
    -- ``teacher_guide.json``, ``lessons/*.json``, ``lessons_index.tsv``,
    ``standards.json`` -- is withheld by default; only ``verification_report.txt``
    is written. Successful exports are written to a temporary directory and only
    then moved into ``--out`` so a standards/remap failure cannot leave a fresh
    GO report beside a stale ``lessons/`` tree.
    """
    from .pdf.page_map import PageMapError

    cfg = _config(args)

    if args.standards and not Path(args.standards).is_file():
        print(f"ERROR: standards file not found: {args.standards}", file=sys.stderr)
        return 2

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    guide = parse_teacher_guide(args.path, cfg)

    with PdfDocument(args.path) as doc:
        report = verify(guide, doc=doc, cfg=cfg, expected_count=args.expect)

    if not report.passed and not args.allow_block:
        # BLOCK path: report only — never imply GO next to old lessons.
        atomic_write_text(out / "verification_report.txt", report.render())
        print(
            f"BLOCK: verification failed ({len(report.fails)} hard check(s)) -- "
            f"trusted output withheld. See {out}/verification_report.txt.",
            file=sys.stderr,
        )
        print(
            "Re-run with --allow-block to write output anyway (for debugging; "
            "downstream commands should not treat it as trusted).",
            file=sys.stderr,
        )
        return 1

    # Parse standards + remap BEFORE any GO artifact lands in --out.
    stds = None
    if args.standards:
        try:
            stds = parse_standards(args.standards)
        except (SpreadsheetStructureError, ValueError, OSError) as e:
            print(f"ERROR: failed to parse standards file: {e}", file=sys.stderr)
            return 1

    try:
        exported = _guide_for_json_export(guide, args.path, cfg)
    except PageMapError as e:
        print(f"ERROR: printed page map failed: {e}", file=sys.stderr)
        return 1

    with tempfile.TemporaryDirectory(prefix="veramynd_export_") as tmp_name:
        tmp = Path(tmp_name)
        lessons_dir = tmp / "lessons"
        lessons_dir.mkdir(parents=True, exist_ok=True)

        atomic_write_text(tmp / "verification_report.txt", report.render())
        atomic_write_text(tmp / "teacher_guide.json", exported.model_dump_json(indent=2))

        for lesson in exported.lessons:
            atomic_write_text(
                lessons_dir / f"{safe_code_filename(lesson.code)}.json",
                lesson.model_dump_json(indent=2) + "\n",
            )

        index = ["code\tpages\tmin\tdeclared_standards\ttitle"]
        for lesson in exported.lessons:
            index.append(
                f"{lesson.code}\t{lesson.page_start}-{lesson.page_end}\t"
                f"{lesson.total_minutes}\t{','.join(lesson.declared_standards)}\t{lesson.title}"
            )
        atomic_write_text(tmp / "lessons_index.tsv", "\n".join(index))

        if stds is not None:
            atomic_write_text(tmp / "standards.json", stds.model_dump_json(indent=2))

        # Promote temp tree into the real output only after everything succeeded.
        # Report is promoted with the lessons so GO never outlives a failed write.
        atomic_replace_dir(lessons_dir, out / "lessons")
        for name in (
            "verification_report.txt",
            "teacher_guide.json",
            "lessons_index.tsv",
            "standards.json",
        ):
            src = tmp / name
            if src.is_file():
                atomic_write_text(out / name, src.read_text(encoding="utf-8"))
        # Drop a stale standards.json if this export did not include standards.
        if stds is None:
            stale_stds = out / "standards.json"
            if stale_stds.is_file():
                stale_stds.unlink()

    print(f"Detected {len(guide.lessons)} lessons -> {out}/")
    print(f"  verification_report.txt      ({report.verdict})")
    print(f"  teacher_guide.json           (full parse)")
    print(f"  lessons/                     ({len(guide.lessons)} files, one per lesson)")
    print(f"  lessons_index.tsv            (summary table)")
    if not report.passed:
        print("  WARNING: --allow-block was set -- output written despite a BLOCK verdict")
    if cfg.export_printed_pages:
        print("  page numbers                 printed footers (not PDF indices)")
    if stds is not None:
        print(f"  standards.json               ({len(stds.standards)} standards)")
    return 0 if report.passed else 1


def cmd_remap_pages(args: argparse.Namespace) -> int:
    """Rewrite existing lesson JSON page fields using the PDF footer map (no re-parse).

    Requires ``--from-pdf-indices`` because printed numbers overlap the PDF index
    range (e.g. printed 39 is also a valid PDF page index) -- auto-detect is unsafe.
    """
    from .models import Lesson, TeacherGuide
    from .pdf.export_pages import for_export, remap_lesson
    from .pdf.page_map import PageMapError, build_printed_page_map

    if not args.from_pdf_indices:
        print(
            "ERROR: pass --from-pdf-indices to confirm lesson JSON still uses PDF "
            "page indices (re-running after a printed remap would double-map).",
            file=sys.stderr,
        )
        return 2

    lessons_dir = Path(args.lessons_dir)
    if not lessons_dir.is_dir():
        print(f"ERROR: lessons dir not found: {lessons_dir}", file=sys.stderr)
        return 2
    try:
        page_map = build_printed_page_map(args.pdf)
    except PageMapError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1

    n = 0
    for path in sorted(lessons_dir.glob("*.json")):
        if path.name == "normalize_progress.json":
            continue
        lesson = Lesson.model_validate_json(path.read_text(encoding="utf-8"))
        remapped = remap_lesson(lesson, page_map)
        atomic_write_text(path, remapped.model_dump_json(indent=2) + "\n")
        n += 1
        print(
            f"{lesson.code}: PDF {lesson.page_start}-{lesson.page_end} "
            f"-> printed {remapped.page_start}-{remapped.page_end}"
        )

    tg = lessons_dir.parent / "teacher_guide.json"
    if tg.is_file() and args.remap_guide:
        guide = TeacherGuide.model_validate_json(tg.read_text(encoding="utf-8"))
        exported = for_export(guide, args.pdf, page_map=page_map)
        atomic_write_text(tg, exported.model_dump_json(indent=2) + "\n")
        print(f"rewrote {tg}")

    # Refresh lessons_index.tsv if present
    index_path = lessons_dir.parent / "lessons_index.tsv"
    if index_path.is_file():
        lines = ["code\tpages\tmin\tdeclared_standards\ttitle"]
        for path in sorted(lessons_dir.glob("G*.json")):
            lesson = Lesson.model_validate_json(path.read_text(encoding="utf-8"))
            lines.append(
                f"{lesson.code}\t{lesson.page_start}-{lesson.page_end}\t"
                f"{lesson.total_minutes}\t{','.join(lesson.declared_standards)}\t{lesson.title}"
            )
        atomic_write_text(index_path, "\n".join(lines) + "\n")
        print(f"rewrote {index_path}")

    print(f"Remapped {n} lesson files using footer map from {args.pdf}")
    return 0


def cmd_verify(args: argparse.Namespace) -> int:
    cfg = _config(args)
    guide = parse_teacher_guide(args.path, cfg)
    with PdfDocument(args.path) as doc:
        report = verify(guide, doc=doc, cfg=cfg, expected_count=args.expect)
    _print_guide_summary(guide)
    print()
    print(report.render())
    return 0 if report.passed else 1


def _require_stage1_go(lessons_dir: Path, *, allow_unverified: bool) -> int | None:
    """Refuse to normalize unless Stage 1 verification reported GO.

    Looks for ``verification_report.txt`` next to ``lessons/``
    (``…/stage1/lessons`` → ``…/stage1/verification_report.txt``).
    Returns an exit code on failure, else None.
    """
    if allow_unverified:
        print(
            "WARNING: --allow-unverified set — normalizing without a Stage 1 GO gate",
            flush=True,
        )
        return None
    report = lessons_dir.parent / "verification_report.txt"
    if not report.is_file():
        print(
            f"ERROR: no Stage 1 verification report at {report}. "
            f"Run export until GO, or pass --allow-unverified (not for production).",
            file=sys.stderr,
        )
        return 2
    last = report.read_text(encoding="utf-8").strip().splitlines()[-1]
    normalized = last.replace("→", "->")
    is_go = "BLOCK" not in normalized and (
        normalized.rstrip().endswith("GO") or "-> GO" in normalized
    )
    if not is_go:
        print(
            f"ERROR: Stage 1 is not GO ({report}). "
            f"Last line: {last!r}. Re-export, or pass --allow-unverified.",
            file=sys.stderr,
        )
        return 1
    return None


def cmd_normalize_lessons(args: argparse.Namespace) -> int:
    """ELA curriculum normalizer: Stage-1 lesson -> schema 2.0-ela (OpenAI)."""
    cfg = _normalize_config(args)
    src = Path(args.lessons_dir)
    if not src.is_dir():
        print(f"ERROR: lessons dir not found: {src}", file=sys.stderr)
        return 2

    gate = _require_stage1_go(src, allow_unverified=getattr(args, "allow_unverified", False))
    if gate is not None:
        return gate

    out = Path(args.out)
    refresh = bool(args.force or args.no_resume)
    try:
        if args.one:
            one = Path(args.one)
            if not one.is_file():
                candidate = src / args.one
                if candidate.is_file():
                    one = candidate
                else:
                    one = src / f"{args.one}.json"
            if not one.is_file():
                print(f"ERROR: lesson file not found: {args.one}", file=sys.stderr)
                return 2
            # Resolve under lessons_dir when possible (no path escape).
            try:
                one.resolve().relative_to(src.resolve())
            except ValueError:
                if one.parent.resolve() != src.resolve():
                    print(
                        f"ERROR: --one path must be inside lessons dir ({src})",
                        file=sys.stderr,
                    )
                    return 2
            norm = normalize_lesson(
                one,
                cfg,
                use_cache=not args.no_cache,
                refresh_cache=refresh and not args.no_cache,
            )
            out.mkdir(parents=True, exist_ok=True)
            dest = out / f"{safe_code_filename(norm.code)}.json"
            atomic_write_text(dest, dump_ela_record_json(norm))
            print(
                f"{norm.resource_id}: {len(norm.what_is_taught)} skills, "
                f"{len(norm.evidence)} evidence -> {dest}"
            )
            preview = norm.objective[:160]
            suffix = "..." if len(norm.objective) > 160 else ""
            print(f"  objective: {preview}{suffix}")
            return 0

        results = normalize_lessons_dir(
            src,
            out,
            cfg,
            use_cache=not args.no_cache,
            resume=not args.no_resume,
            force=args.force,
            max_workers=args.max_workers,
        )
        print(f"Normalized {len(results)} lessons -> {out}/")
        for n in results[:5]:
            print(
                f"  {n.resource_id}: {len(n.what_is_taught)} skills, "
                f"{len(n.evidence)} evidence"
            )
        if len(results) > 5:
            print(f"  ... {len(results) - 5} more")
        return 0
    except LlmError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1
    except (OSError, ValueError, RuntimeError) as e:
        print(f"ERROR: {e}", file=sys.stderr)
        print("Re-run the same command to resume from the last completed lesson.", file=sys.stderr)
        return 1


def cmd_normalize_standards(args: argparse.Namespace) -> int:
    """Normalize Stage-1 standards.json leaves into retrieval records."""
    cfg = _normalize_config(args)
    src = Path(args.standards_json)
    if not src.is_file():
        print(f"ERROR: standards JSON not found: {src}", file=sys.stderr)
        return 2

    out = Path(args.out)
    refresh = bool(args.force or args.no_resume)
    try:
        tree = GradeStandards.model_validate_json(src.read_text(encoding="utf-8"))
        if args.one:
            code = args.one.strip()
            matches = [s for s in tree.standards if s.code == code]
            if not matches:
                print(f"ERROR: standard code not found: {code}", file=sys.stderr)
                return 2
            std = matches[0]
            if std.level not in (StandardLevel.STANDARD, StandardLevel.SUBSTANDARD):
                print(
                    f"ERROR: {code} level={std.level.value} is not a scorable leaf "
                    "(normalize standard/substandard only)",
                    file=sys.stderr,
                )
                return 2
            norm = normalize_standard(
                std,
                tree,
                cfg,
                use_cache=not args.no_cache,
                refresh_cache=refresh and not args.no_cache,
            )
            out.mkdir(parents=True, exist_ok=True)
            from .normalize.standard import safe_standard_filename

            dest = out / f"{safe_standard_filename(norm.standard_code)}.json"
            atomic_write_text(dest, dump_normalized_standard_json(norm))
            print(
                f"{norm.standard_code}: {norm.domain.primary}; "
                f"{len(norm.skill_clauses)} skills -> {dest}"
            )
            preview = norm.competency_statement[:160]
            suffix = "..." if len(norm.competency_statement) > 160 else ""
            print(f"  competency: {preview}{suffix}")
            return 0

        results = normalize_standards_tree(
            tree,
            out,
            cfg,
            use_cache=not args.no_cache,
            resume=not args.no_resume,
            force=args.force,
            max_workers=args.max_workers,
            limit=args.limit,
        )
        print(f"Normalized {len(results)} standards -> {out}/")
        for n in results[:5]:
            print(
                f"  {n.standard_code}: {n.domain.primary}; "
                f"{len(n.skill_clauses)} skills"
            )
        if len(results) > 5:
            print(f"  ... {len(results) - 5} more")
        return 0 if results else 1
    except LlmError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1
    except (OSError, ValueError, RuntimeError) as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1


def cmd_repair_normalized(args: argparse.Namespace) -> int:
    """Re-apply ELA sanitizers to existing normalize JSON (no LLM calls)."""
    lessons = Path(args.lessons_dir)
    normalize_dir = Path(args.normalize_dir)
    if not lessons.is_dir():
        print(f"ERROR: lessons dir not found: {lessons}", file=sys.stderr)
        return 2
    if not normalize_dir.is_dir():
        print(f"ERROR: normalize dir not found: {normalize_dir}", file=sys.stderr)
        return 2
    try:
        summary = repair_normalized_dir(lessons, normalize_dir)
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1
    if summary["failed"]:
        return 1
    return 0


def cmd_chunk_lessons(args: argparse.Namespace) -> int:
    """Build hierarchical chunks from Stage-1 + normalize (no LLM)."""
    lessons = Path(args.lessons_dir)
    normalize_dir = Path(args.normalize_dir)
    out = Path(args.out)
    if not lessons.is_dir():
        print(f"ERROR: lessons dir not found: {lessons}", file=sys.stderr)
        return 2
    if not normalize_dir.is_dir():
        print(f"ERROR: normalize dir not found: {normalize_dir}", file=sys.stderr)
        return 2
    try:
        manifest = chunk_lessons_dir(lessons, normalize_dir, out)
    except (OSError, ValueError, RuntimeError) as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1
    if manifest.get("failed"):
        return 1
    return 0


def cmd_embed_chunks(args: argparse.Namespace) -> int:
    """Embed lesson/instructional chunks with OpenAI and upsert into Qdrant."""
    chunks = Path(args.chunks_dir)
    out = Path(args.out)
    if not chunks.is_dir():
        print(f"ERROR: chunks dir not found: {chunks}", file=sys.stderr)
        return 2
    try:
        manifest = embed_chunks_to_qdrant(
            chunks,
            out,
            model=args.model,
            dimensions=args.dimensions,
            collection=args.collection,
            qdrant_url=args.qdrant_url,
            qdrant_api_key=args.qdrant_api_key,
            qdrant_path=args.qdrant_path,
            recreate=bool(args.recreate),
            resource_ids=set(args.resource_id) if args.resource_id else None,
        )
    except (EmbedError, LlmError) as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1
    except (OSError, ValueError, RuntimeError) as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1
    if manifest.get("failed"):
        return 1
    return 0


def cmd_embed_standards(args: argparse.Namespace) -> int:
    """Embed normalized standards with OpenAI and upsert into Qdrant."""
    src = Path(args.standards_dir)
    out = Path(args.out)
    if not src.is_dir():
        print(f"ERROR: standards dir not found: {src}", file=sys.stderr)
        return 2
    try:
        manifest = embed_standards_to_qdrant(
            src,
            out,
            model=args.model,
            dimensions=args.dimensions,
            collection=args.collection,
            qdrant_url=args.qdrant_url,
            qdrant_api_key=args.qdrant_api_key,
            qdrant_path=args.qdrant_path,
            recreate=bool(args.recreate),
            codes=set(args.code) if args.code else None,
        )
    except (EmbedError, LlmError) as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1
    except (OSError, ValueError, RuntimeError) as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1
    if manifest.get("failed"):
        return 1
    return 0


def cmd_smoke_retrieve_standards(args: argparse.Namespace) -> int:
    """Query veramynd_standards with a lesson chunk (or free text) for a smoke check."""
    query = (args.query or "").strip()
    if args.chunk_file:
        path = Path(args.chunk_file)
        if not path.is_file():
            print(f"ERROR: chunk file not found: {path}", file=sys.stderr)
            return 2
        data = json.loads(path.read_text(encoding="utf-8"))
        if args.family == "lesson":
            row = data.get("lesson_chunk") or {}
            query = (row.get("text") or "").strip()
            label = row.get("chunk_id") or path.name
        else:
            blocks = data.get("instructional_chunks") or []
            if not blocks:
                print(f"ERROR: no instructional_chunks in {path}", file=sys.stderr)
                return 2
            # Prefer a phonics-ish block when present; else first block.
            chosen = blocks[0]
            for b in blocks:
                text = (b.get("text") or "")
                if any(
                    k in text.lower()
                    for k in ("phon", "syllable", "decode", "blend", "digraph")
                ):
                    chosen = b
                    break
            query = (chosen.get("text") or "").strip()
            label = chosen.get("chunk_id") or path.name
        print(f"Query source: {label} ({args.family})", flush=True)
    if not query:
        print("ERROR: provide --query TEXT or --chunk-file PATH", file=sys.stderr)
        return 2
    try:
        hits = query_standards_by_text(
            query,
            limit=args.limit,
            model=args.model,
            dimensions=args.dimensions,
            collection=args.collection,
            qdrant_url=args.qdrant_url,
            qdrant_api_key=args.qdrant_api_key,
            qdrant_path=args.qdrant_path,
        )
    except (EmbedError, LlmError) as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1
    except (OSError, ValueError, RuntimeError) as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1

    print(f"Top {len(hits)} standards:", flush=True)
    for i, h in enumerate(hits, start=1):
        print(
            f"  {i}. {h.get('standard_code')}  score={h.get('score'):.4f}  "
            f"domain={h.get('domain_primary')!r}  label={h.get('label')!r}",
            flush=True,
        )
    return 0


def cmd_cache_prune(args: argparse.Namespace) -> int:
    """Report (and optionally delete) cache entries orphaned by a version bump."""
    from .cache_maintenance import (
        apply_prune,
        installed_docling_version,
        scan_docling_cache,
        scan_normalize_cache,
    )
    from .normalize.lesson import PROMPT_VERSION, _resolve_cache_dir
    from .pdf.docling_parser import resolve_docling_cache_dir

    defaults = Config()
    norm_dir = (
        Path(args.normalize_cache_dir)
        if args.normalize_cache_dir
        else _resolve_cache_dir(defaults.normalize.cache_dir)
    )
    docling_dir = (
        Path(args.docling_cache_dir)
        if args.docling_cache_dir
        else resolve_docling_cache_dir(defaults)
    )

    norm_result = scan_normalize_cache(norm_dir, current_prompt_version=PROMPT_VERSION)
    docling_version = installed_docling_version()
    docling_result = scan_docling_cache(docling_dir, current_docling_version=docling_version)

    def _report(name: str, cache_dir: Path, result) -> None:
        print(f"{name} ({cache_dir}):")
        print(f"  current : {len(result.kept)}")
        print(f"  stale   : {len(result.stale)} ({result.stale_bytes:,} bytes)")
        if result.unreadable:
            print(f"  unreadable (left alone, needs a look): {len(result.unreadable)}")
            for p in result.unreadable[:5]:
                print(f"    {p.name}")

    print(f"normalize prompt_version: {PROMPT_VERSION}")
    _report("normalize cache", norm_dir, norm_result)
    print(f"docling version: {docling_version or '(not installed -- cannot classify; nothing marked stale)'}")
    _report("docling cache", docling_dir, docling_result)

    total_stale = len(norm_result.stale) + len(docling_result.stale)
    if not args.apply:
        if total_stale:
            print(f"\nDry run -- {total_stale} stale file(s) not deleted. Re-run with --apply to delete them.")
        return 0

    deleted = apply_prune(norm_result) + apply_prune(docling_result)
    print(f"\nDeleted {deleted} stale cache file(s).")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="veramynd_parser", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    g = sub.add_parser("guide", help="parse a teacher-guide PDF")
    g.add_argument("path")
    g.add_argument("--json", help="write full result as JSON")
    _add_parse_flags(g)
    g.set_defaults(func=cmd_guide)

    s = sub.add_parser("stds", help="parse a standards spreadsheet")
    s.add_argument("path")
    s.add_argument("--json", help="write full result as JSON")
    s.set_defaults(func=cmd_standards)

    v = sub.add_parser("verify", help="parse and run the safety-net verifier")
    v.add_argument("path")
    v.add_argument("--expect", type=int, default=None, help="expected lesson count")
    _add_parse_flags(v)
    v.set_defaults(func=cmd_verify)

    e = sub.add_parser("export", help="parse, verify, and write all detected lessons to a folder")
    e.add_argument("path")
    e.add_argument(
        "--out",
        default="output/stage1",
        help="Stage 1 output folder (default: output/stage1)",
    )
    e.add_argument("--standards", default=None, help="also parse a standards spreadsheet")
    e.add_argument("--expect", type=int, default=None, help="expected lesson count")
    e.add_argument(
        "--allow-block",
        action="store_true",
        help=(
            "write output even if verification BLOCKs (a hard check FAILed). "
            "Off by default -- trusted output (teacher_guide.json, lessons/*.json, "
            "lessons_index.tsv, standards.json) is withheld on BLOCK so a caller "
            "that doesn't check the exit code can't silently pick up unverified "
            "data; verification_report.txt is always written."
        ),
    )
    _add_parse_flags(e)
    e.set_defaults(func=cmd_export)

    n = sub.add_parser(
        "normalize-lessons",
        help="ELA curriculum normalizer: lessons -> schema 2.0-ela (OpenAI, resumable)",
    )
    n.add_argument(
        "lessons_dir",
        help="directory of per-lesson JSON files (e.g. output/stage1/lessons)",
    )
    n.add_argument(
        "--out",
        default="output/normalize",
        help="output folder for NormalizedLesson JSON (default: output/normalize)",
    )
    n.add_argument(
        "--one",
        default=None,
        help="normalize only one lesson (code or path), e.g. G1M2U1L1",
    )
    n.add_argument(
        "--model",
        default=None,
        help="override OpenAI model id (default: OPENAI_MODEL env or gpt-4.1-mini)",
    )
    n.add_argument(
        "--cache-dir",
        default=None,
        help="content-addressed cache dir (default: .normalize_cache)",
    )
    n.add_argument(
        "--max-tokens",
        type=int,
        default=None,
        help=(
            "response token cap (default: 8192 for ELA evidence records). "
            "Raise this if dense lessons hit finish_reason=length "
            "(truncation) -- logged explicitly when it happens."
        ),
    )
    n.add_argument(
        "--no-cache",
        action="store_true",
        help="bypass read/write of the content-addressed LLM cache",
    )
    n.add_argument(
        "--no-resume",
        action="store_true",
        help=(
            "call the API fresh for every lesson, bypassing the content-addressed "
            "cache entirely (still writes progress file); same effect as --force"
        ),
    )
    n.add_argument(
        "--force",
        action="store_true",
        help="re-normalize every lesson even if the cache already has a hit for it",
    )
    n.add_argument(
        "--max-workers",
        type=int,
        default=1,
        help="lessons to normalize concurrently (default: 1, sequential); "
        "pick a value your OpenAI rate limits actually allow",
    )
    n.add_argument(
        "--allow-unverified",
        action="store_true",
        help=(
            "allow normalize without a Stage 1 GO verification_report.txt "
            "(debug only — not for production)"
        ),
    )
    n.set_defaults(func=cmd_normalize_lessons)

    ns = sub.add_parser(
        "normalize-standards",
        help=(
            "ELA standards normalizer: Stage-1 standards.json -> schema 1.0-std "
            "(OpenAI; standard/substandard leaves; resumable, cached)"
        ),
    )
    ns.add_argument(
        "standards_json",
        help="Stage-1 standards.json (e.g. output/stage1/standards.json)",
    )
    ns.add_argument(
        "--out",
        default="output/normalize_standards",
        help="output folder for NormalizedStandard JSON (default: output/normalize_standards)",
    )
    ns.add_argument(
        "--one",
        default=None,
        help="normalize only one code, e.g. 1.F.PA.4 or 1.F.PA.4.d",
    )
    ns.add_argument(
        "--limit",
        type=int,
        default=None,
        help="normalize only the first N scorable leaves (smoke / cost control)",
    )
    ns.add_argument(
        "--model",
        default=None,
        help="override OpenAI model id (default: OPENAI_MODEL env or gpt-4.1-mini)",
    )
    ns.add_argument(
        "--cache-dir",
        default=None,
        help="content-addressed cache dir (default: .normalize_cache/standards)",
    )
    ns.add_argument(
        "--max-tokens",
        type=int,
        default=None,
        help="response token cap (default: 4096 for standards drafts)",
    )
    ns.add_argument(
        "--no-cache",
        action="store_true",
        help="bypass read/write of the content-addressed LLM cache",
    )
    ns.add_argument(
        "--no-resume",
        action="store_true",
        help="call the API fresh for every standard (same effect as --force for cache)",
    )
    ns.add_argument(
        "--force",
        action="store_true",
        help="re-normalize every standard even if the cache already has a hit",
    )
    ns.add_argument(
        "--max-workers",
        type=int,
        default=1,
        help="standards to normalize concurrently (default: 1)",
    )
    ns.set_defaults(func=cmd_normalize_standards)

    rp = sub.add_parser(
        "repair-normalized",
        help=(
            "re-apply ELA sanitizers to existing normalize JSON without LLM calls "
            "(pacing from agenda, redact standard codes, enforce verbatim evidence)"
        ),
    )
    rp.add_argument(
        "lessons_dir",
        help="Stage-1 lessons dir (e.g. output/stage1/lessons)",
    )
    rp.add_argument(
        "--normalize-dir",
        default="output/normalize",
        help="normalize output dir to repair in place (default: output/normalize)",
    )
    rp.set_defaults(func=cmd_repair_normalized)

    ch = sub.add_parser(
        "chunk-lessons",
        help=(
            "build production hierarchical chunks from Stage-1 lessons + normalize "
            "(lesson + instructional blocks + evidence join pointers)"
        ),
    )
    ch.add_argument(
        "lessons_dir",
        help="Stage-1 lessons dir (e.g. output/stage1/lessons)",
    )
    ch.add_argument(
        "--normalize-dir",
        default="output/normalize",
        help="normalize records dir (default: output/normalize)",
    )
    ch.add_argument(
        "--out",
        default="output/chunks",
        help="chunk output folder (default: output/chunks)",
    )
    ch.set_defaults(func=cmd_chunk_lessons)

    em = sub.add_parser(
        "embed-chunks",
        help=(
            "embed lesson/instructional chunks with OpenAI "
            f"{DEFAULT_EMBEDDING_MODEL} and upsert into Qdrant"
        ),
    )
    em.add_argument(
        "chunks_dir",
        nargs="?",
        default="output/chunks",
        help="chunk dir with by_lesson/ (default: output/chunks)",
    )
    em.add_argument(
        "--out",
        default="output/embeddings",
        help="manifest/progress output folder (default: output/embeddings)",
    )
    em.add_argument(
        "--model",
        default=DEFAULT_EMBEDDING_MODEL,
        help=f"OpenAI embedding model (default: {DEFAULT_EMBEDDING_MODEL})",
    )
    em.add_argument(
        "--dimensions",
        type=int,
        default=DEFAULT_DIMENSIONS,
        help=f"embedding dimensions (default: {DEFAULT_DIMENSIONS})",
    )
    em.add_argument(
        "--collection",
        default=None,
        help=f"Qdrant collection name (default: env QDRANT_COLLECTION or {DEFAULT_COLLECTION})",
    )
    em.add_argument(
        "--qdrant-url",
        default=None,
        help="Qdrant server URL (default: env QDRANT_URL; else local path mode)",
    )
    em.add_argument(
        "--qdrant-api-key",
        default=None,
        help="Qdrant API key (default: env QDRANT_API_KEY). Prefer .env over CLI.",
    )
    em.add_argument(
        "--qdrant-path",
        default=None,
        help="local Qdrant storage path when URL unset (default: .qdrant_data)",
    )
    em.add_argument(
        "--recreate",
        action="store_true",
        help="delete and recreate the collection before upsert",
    )
    em.add_argument(
        "--resource-id",
        action="append",
        default=[],
        help="limit embed/upsert to one lesson code (repeatable), e.g. --resource-id G1M2U2L1",
    )
    em.set_defaults(func=cmd_embed_chunks)

    es = sub.add_parser(
        "embed-standards",
        help=(
            "embed normalized standard leaves with OpenAI "
            f"{DEFAULT_EMBEDDING_MODEL} into Qdrant "
            f"(default collection {DEFAULT_STANDARDS_COLLECTION})"
        ),
    )
    es.add_argument(
        "standards_dir",
        nargs="?",
        default="output/normalize_standards",
        help="normalize_standards dir (default: output/normalize_standards)",
    )
    es.add_argument(
        "--out",
        default="output/embeddings",
        help="manifest/progress output folder (default: output/embeddings)",
    )
    es.add_argument(
        "--model",
        default=DEFAULT_EMBEDDING_MODEL,
        help=f"OpenAI embedding model (default: {DEFAULT_EMBEDDING_MODEL})",
    )
    es.add_argument(
        "--dimensions",
        type=int,
        default=DEFAULT_DIMENSIONS,
        help=f"embedding dimensions (default: {DEFAULT_DIMENSIONS})",
    )
    es.add_argument(
        "--collection",
        default=None,
        help=(
            f"Qdrant collection (default: env QDRANT_STANDARDS_COLLECTION or "
            f"{DEFAULT_STANDARDS_COLLECTION})"
        ),
    )
    es.add_argument(
        "--qdrant-url",
        default=None,
        help="Qdrant server URL (default: env QDRANT_URL; else local path mode)",
    )
    es.add_argument(
        "--qdrant-api-key",
        default=None,
        help="Qdrant API key (default: env QDRANT_API_KEY). Prefer .env over CLI.",
    )
    es.add_argument(
        "--qdrant-path",
        default=None,
        help="local Qdrant storage path when URL unset (default: .qdrant_data)",
    )
    es.add_argument(
        "--recreate",
        action="store_true",
        help="delete and recreate the collection before upsert",
    )
    es.add_argument(
        "--code",
        action="append",
        default=[],
        help="limit embed/upsert to one standard code (repeatable), e.g. --code 1.F.PA.4",
    )
    es.set_defaults(func=cmd_embed_standards)

    sm = sub.add_parser(
        "smoke-retrieve-standards",
        help=(
            "smoke-test: embed a lesson chunk (or free text) and query "
            f"{DEFAULT_STANDARDS_COLLECTION} for nearest GA codes"
        ),
    )
    sm.add_argument(
        "--chunk-file",
        default=None,
        help="path to a by_lesson/*.json bundle (uses lesson or instructional text)",
    )
    sm.add_argument(
        "--family",
        choices=("lesson", "instructional"),
        default="lesson",
        help="which chunk text to query when --chunk-file is set (default: lesson)",
    )
    sm.add_argument(
        "--query",
        default=None,
        help="free-text query (alternative to --chunk-file)",
    )
    sm.add_argument(
        "--limit",
        type=int,
        default=8,
        help="top-k standards to print (default: 8)",
    )
    sm.add_argument(
        "--model",
        default=DEFAULT_EMBEDDING_MODEL,
        help=f"OpenAI embedding model (default: {DEFAULT_EMBEDDING_MODEL})",
    )
    sm.add_argument(
        "--dimensions",
        type=int,
        default=DEFAULT_DIMENSIONS,
        help=f"embedding dimensions (default: {DEFAULT_DIMENSIONS})",
    )
    sm.add_argument(
        "--collection",
        default=None,
        help=(
            f"Qdrant collection (default: env QDRANT_STANDARDS_COLLECTION or "
            f"{DEFAULT_STANDARDS_COLLECTION})"
        ),
    )
    sm.add_argument("--qdrant-url", default=None, help="Qdrant server URL")
    sm.add_argument("--qdrant-api-key", default=None, help="Qdrant API key")
    sm.add_argument("--qdrant-path", default=None, help="local Qdrant path")
    sm.set_defaults(func=cmd_smoke_retrieve_standards)

    r = sub.add_parser(
        "remap-pages",
        help="rewrite existing lesson JSON pages from PDF indices -> printed footers",
    )
    r.add_argument("pdf", help="teacher-guide PDF used to build the footer map")
    r.add_argument(
        "--lessons-dir",
        required=True,
        help="directory of per-lesson JSON files still using PDF page indices",
    )
    r.add_argument(
        "--from-pdf-indices",
        action="store_true",
        help="required confirmation that inputs use PDF indices (not already remapped)",
    )
    r.add_argument(
        "--remap-guide",
        action="store_true",
        default=True,
        help="also rewrite ../teacher_guide.json if present (default: on)",
    )
    r.add_argument(
        "--no-remap-guide",
        action="store_false",
        dest="remap_guide",
        help="skip teacher_guide.json",
    )
    r.set_defaults(func=cmd_remap_pages)

    cp = sub.add_parser(
        "cache-prune",
        help="report/delete normalize+docling cache entries orphaned by a version bump",
    )
    cp.add_argument(
        "--normalize-cache-dir",
        default=None,
        help="default: NormalizeConfig.cache_dir (.normalize_cache, package-root-relative)",
    )
    cp.add_argument(
        "--docling-cache-dir",
        default=None,
        help="default: Config.docling_cache_dir (.docling_cache, package-root-relative)",
    )
    cp.add_argument(
        "--apply",
        action="store_true",
        help="actually delete stale entries (default: dry-run report only)",
    )
    cp.set_defaults(func=cmd_cache_prune)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())

