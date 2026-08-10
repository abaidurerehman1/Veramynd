"""Stage-1 provenance gates for the CLI.

Every downstream stage (normalize, chunk, embed, retrieve, judge) must refuse
to silently consume Stage-1 output that verification marked BLOCK — otherwise
a bad export propagates through the pipeline with no trace. This module holds
that trust-gate logic on its own so ``cli.py`` stays a thin command dispatcher
rather than absorbing verification-provenance rules alongside every command's
argument wiring.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from .verify.verifier import VERDICT_FILENAME


def legacy_report_verdict(report_path: Path) -> bool | None:
    """Best-effort GO/BLOCK read from a legacy text verification report
    (exports made before ``verification_verdict.json`` existed). Returns
    True (GO), False (BLOCK), or None if the file is missing/empty/unreadable.
    """
    if not report_path.is_file():
        return None
    lines = [ln for ln in report_path.read_text(encoding="utf-8").splitlines() if ln.strip()]
    if not lines:
        return None
    last = lines[-1].replace("→", "->")
    if "BLOCK" in last:
        return False
    if last.rstrip().endswith("GO") or "-> GO" in last:
        return True
    return None


def require_stage1_go(lessons_dir: Path, *, allow_unverified: bool) -> int | None:
    """Refuse to consume Stage-1 lessons unless verification reported GO.

    Reads the machine-readable ``verification_verdict.json`` next to
    ``lessons/`` (``…/stage1/lessons`` → ``…/stage1/verification_verdict.json``).
    Falls back to parsing the legacy text report only when the verdict file is
    absent (exports made before it existed). Returns an exit code on failure,
    else None.
    """
    if allow_unverified:
        print(
            "WARNING: --allow-unverified set — proceeding without a Stage 1 GO gate",
            flush=True,
        )
        return None

    verdict_path = lessons_dir.parent / VERDICT_FILENAME
    if verdict_path.is_file():
        try:
            data = json.loads(verdict_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            print(
                f"ERROR: unreadable Stage 1 verdict ({verdict_path}): {e}. "
                f"Re-export, or pass --allow-unverified.",
                file=sys.stderr,
            )
            return 1
        if not isinstance(data, dict):
            data = {}
        verdict = data.get("verdict")
        if verdict != "GO":
            print(
                f"ERROR: Stage 1 is not GO ({verdict_path}: verdict={verdict!r}, "
                f"{data.get('fail_count', '?')} hard check(s) failed). "
                f"Re-export, or pass --allow-unverified.",
                file=sys.stderr,
            )
            return 1
        return None

    # Legacy fallback: exports made before verification_verdict.json existed.
    report = lessons_dir.parent / "verification_report.txt"
    if not report.is_file():
        print(
            f"ERROR: no Stage 1 verdict at {verdict_path} and no legacy report at "
            f"{report}. Run export until GO, or pass --allow-unverified "
            f"(not for production).",
            file=sys.stderr,
        )
        return 2
    print(
        f"WARNING: no {VERDICT_FILENAME} next to {lessons_dir} — falling back to "
        f"parsing the legacy text report. Re-export to write the verdict file.",
        flush=True,
    )
    lines = [ln for ln in report.read_text(encoding="utf-8").splitlines() if ln.strip()]
    if not lines:
        print(
            f"ERROR: Stage 1 verification report is empty ({report}). "
            f"Re-export until GO, or pass --allow-unverified.",
            file=sys.stderr,
        )
        return 1
    last = lines[-1]
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


def require_chunks_trusted(chunks_dir: Path, *, allow_unverified: bool) -> int | None:
    """Refuse to embed chunks whose manifest says Stage 1 was not GO.

    ``chunk-lessons`` stamps ``stage1_verdict`` into ``chunk_manifest.json``.
    Manifests written before that field existed are tolerated with a warning.
    Returns an exit code on failure, else None.
    """
    if allow_unverified:
        print(
            "WARNING: --allow-unverified set — embedding without a Stage 1 GO gate",
            flush=True,
        )
        return None
    manifest_path = chunks_dir / "chunk_manifest.json"
    if not manifest_path.is_file():
        print(
            f"WARNING: no chunk_manifest.json under {chunks_dir} — cannot confirm "
            f"Stage 1 verification. Re-run chunk-lessons to stamp provenance.",
            flush=True,
        )
        return None
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        print(f"ERROR: unreadable chunk manifest ({manifest_path}): {e}", file=sys.stderr)
        return 1
    verdict = manifest.get("stage1_verdict") if isinstance(manifest, dict) else None
    if verdict is None:
        print(
            f"WARNING: {manifest_path} predates stage1_verdict stamping — cannot "
            f"confirm Stage 1 verification. Re-run chunk-lessons to stamp it.",
            flush=True,
        )
        return None
    if verdict != "GO":
        print(
            f"ERROR: chunks were built from unverified Stage 1 output "
            f"({manifest_path}: stage1_verdict={verdict!r}). Re-export until GO and "
            f"re-run chunk-lessons, or pass --allow-unverified (not for production).",
            file=sys.stderr,
        )
        return 1
    return None


def warn_untrusted_input_file(path: str | None, kind: str) -> int | None:
    """Soft gate for single-file inputs to retrieve/judge.

    For a Stage-1 lesson file (``…/lessons/X.json``) checks the sibling
    ``verification_verdict.json``; for a chunk bundle (``…/by_lesson/X.json``)
    checks ``chunk_manifest.json``'s ``stage1_verdict``. Ad-hoc files with no
    provenance artifact are allowed (debugging is legitimate); a provenance
    artifact that says BLOCK/unverified is a hard error. Returns an exit code
    on failure, else None.
    """
    if not path:
        return None
    # Resolve so symlinked/relative inputs are judged by their real location,
    # and only apply the check when the file sits in the expected layout
    # (…/lessons/X.json, …/by_lesson/X.json). A bare relative name would
    # otherwise walk up to cwd lexically and match whatever provenance file
    # happens to live there — hard-failing on genuinely ad-hoc inputs.
    p = Path(path).resolve()
    expected_parent = "lessons" if kind == "lesson" else "by_lesson"
    if p.parent.name != expected_parent:
        return None
    if kind == "lesson":
        verdict_path = p.parent.parent / VERDICT_FILENAME
        if not verdict_path.is_file():
            # Legacy exports (made before verification_verdict.json existed)
            # still have a text report next to lessons/ — a BLOCK there used
            # to pass this gate silently because only the JSON verdict's
            # absence was checked, treating a real legacy BLOCK the same as
            # a genuinely ad-hoc file with no provenance at all.
            legacy = p.parent.parent / "verification_report.txt"
            if legacy_report_verdict(legacy) is False:
                print(
                    f"ERROR: {p} comes from a Stage 1 export that is not GO "
                    f"(legacy report {legacy} says BLOCK). Re-export until GO, "
                    f"or pass --allow-unverified.",
                    file=sys.stderr,
                )
                return 1
            return None
        try:
            data = json.loads(verdict_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return None
        verdict = data.get("verdict") if isinstance(data, dict) else None
        if verdict is not None and verdict != "GO":
            print(
                f"ERROR: {p} comes from a Stage 1 export that is not GO "
                f"({verdict_path}: verdict={verdict!r}). Re-export until GO, "
                f"or pass --allow-unverified.",
                file=sys.stderr,
            )
            return 1
        return None
    # chunk bundle
    manifest_path = p.parent.parent / "chunk_manifest.json"
    if not manifest_path.is_file():
        return None
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    verdict = manifest.get("stage1_verdict") if isinstance(manifest, dict) else None
    if verdict is not None and verdict != "GO":
        print(
            f"ERROR: {p} was chunked from unverified Stage 1 output "
            f"({manifest_path}: stage1_verdict={verdict!r}). Re-export until GO and "
            f"re-run chunk-lessons, or pass --allow-unverified.",
            file=sys.stderr,
        )
        return 1
    return None
