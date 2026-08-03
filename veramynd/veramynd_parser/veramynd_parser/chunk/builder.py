"""Build production hierarchical chunks from Stage-1 + normalize records."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from pydantic import ValidationError

from ..models import Lesson
from ..normalize.models import NONE_OBSERVED, NormalizedLesson, parse_ela_record
from ..paths import iter_lesson_json_files
from ..text_utils import atomic_write_text, safe_code_filename
from .models import (
    CHUNK_SCHEMA_VERSION,
    EvidencePointer,
    InstructionalChunk,
    LessonChunk,
    LessonChunkBundle,
    dump_bundle_json,
)

# Example EL Education labels — informational only. K–12 / multi-publisher
# chunking accepts any non-empty Stage-1 section string + letter.
KNOWN_EL_SECTIONS = frozenset({"Opening", "Work Time", "Closing and Assessment"})
# Back-compat alias (do not use as an allowlist).
CANONICAL_SECTIONS = KNOWN_EL_SECTIONS

_LOCATION_BLOCK = re.compile(r"^\s*(?P<section>.+?)\s+(?P<letter>[A-Z])\b")
_LETTER = re.compile(r"^[A-Z]$")
_SECTION_MAX_LEN = 120

PROGRESS_NAME = "chunk_progress.json"
MANIFEST_NAME = "chunk_manifest.json"


class ChunkBuildError(RuntimeError):
    """Raised when one or more lessons failed to chunk.

    The manifest/progress files are still written for diagnostics, but this is
    raised afterward so a caller (the CLI, or embed) cannot silently proceed
    with an incomplete chunk set just because it forgot to inspect
    ``manifest["failed"]``.
    """


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def source_fingerprint(stage1_text: str, normalize_text: str) -> str:
    """Lineage key: schema + Stage-1 JSON + normalize JSON (byte-stable)."""
    return _sha256_text(
        f"{CHUNK_SCHEMA_VERSION}\0{stage1_text}\0{normalize_text}"
    )


def normalize_section_label(section: str) -> str:
    """Trim Stage-1 section labels for stable chunk IDs (publisher-agnostic)."""
    return " ".join((section or "").split())


def validate_block_identity(resource_id: str, section: str, letter: str) -> tuple[str, str]:
    """Require a usable section+letter from Stage-1; no publisher-specific allowlist."""
    section = normalize_section_label(section)
    letter = (letter or "").strip()
    if not section:
        raise ValueError(f"{resource_id}: instructional block missing section")
    if len(section) > _SECTION_MAX_LEN:
        raise ValueError(
            f"{resource_id}: section label too long ({len(section)} > {_SECTION_MAX_LEN})"
        )
    if not _LETTER.match(letter):
        raise ValueError(
            f"{resource_id}: instructional block letter must be A–Z, got {letter!r}"
        )
    return section, letter


def lesson_chunk_id(resource_id: str) -> str:
    return f"{resource_id}#lesson"


def block_chunk_id(resource_id: str, section: str, letter: str) -> str:
    return f"{resource_id}#{section}#{letter}"


def evidence_pointer_id(resource_id: str, index: int) -> str:
    return f"{resource_id}#evidence#{index}"


def build_lesson_text(norm: NormalizedLesson) -> str:
    """Compact competency text from the normalize record."""
    lines: list[str] = []
    secondary = ", ".join(norm.domain.secondary) if norm.domain.secondary else "none"
    lines.append(f"Domain primary: {norm.domain.primary}")
    lines.append(f"Domain secondary: {secondary}")
    sp = norm.subject_profile
    lines.append(f"Mode: {sp.mode}")
    lines.append(f"Genre: {sp.genre}")
    if norm.objective.strip():
        lines.append(f"Objective: {norm.objective.strip()}")
    if norm.what_is_taught:
        lines.append("Skills taught:")
        for item in norm.what_is_taught:
            emp = f", {item.emphasis}" if item.emphasis else ""
            lines.append(f"- {item.skill} ({item.cognitive_demand}{emp})")
    action_lines: list[str] = []
    for key in (
        "recognition_identification",
        "oral_production",
        "written_production",
        "matching_sorting_sequencing",
        "procedural_application",
        "investigation_handson",
        "representation_modeling",
        "reasoning_explanation",
        "comprehension_response",
    ):
        val = (getattr(norm.student_actions, key, "") or "").strip()
        if val and val != NONE_OBSERVED:
            action_lines.append(f"- {key}: {val}")
    if action_lines:
        lines.append("Student actions:")
        lines.extend(action_lines)
    return "\n".join(lines).strip()


def build_block_text(
    *,
    section: str,
    letter: str,
    title: str,
    steps: list[str],
) -> str:
    header = f"[{section} {letter}]"
    if title.strip():
        header = f"{header} {title.strip()}"
    body = "\n".join(f"- {s.strip()}" for s in steps if (s or "").strip())
    return f"{header}\n{body}".strip() if body else header


def _parse_location(location: str) -> tuple[str, str] | None:
    m = _LOCATION_BLOCK.match(location or "")
    if not m:
        return None
    return m.group("section").strip(), m.group("letter").strip()


def build_lesson_bundle(
    lesson: Lesson,
    norm: NormalizedLesson,
) -> LessonChunkBundle:
    """Build lesson + instructional + evidence-pointer chunks for one code."""
    resource_id = lesson.code
    if norm.resource_id and norm.resource_id != resource_id:
        raise ValueError(
            f"resource_id mismatch: stage1={resource_id!r} normalize={norm.resource_id!r}"
        )

    lesson_text = build_lesson_text(norm)
    lesson_chunk = LessonChunk(
        chunk_id=lesson_chunk_id(resource_id),
        resource_id=resource_id,
        text=lesson_text,
        content_hash=_sha256_text(lesson_text),
        metadata={
            "grade": lesson.grade,
            "module": lesson.module,
            "unit": lesson.unit,
            "lesson": lesson.lesson,
            "title": lesson.title,
            "domain_primary": norm.domain.primary,
            "domain_secondary": list(norm.domain.secondary),
            "mode": norm.subject_profile.mode,
            "genre": norm.subject_profile.genre,
            "prompt_version": norm.prompt_version,
            "page_start": lesson.page_start,
            "page_end": lesson.page_end,
        },
    )

    instructional: list[InstructionalChunk] = []
    block_ids: set[str] = set()
    for block in lesson.instructional_blocks:
        section, letter = validate_block_identity(
            resource_id, block.section or "", block.letter or ""
        )
        steps = [s for s in (block.steps or []) if (s or "").strip()]
        if not steps:
            raise ValueError(
                f"{resource_id}: empty steps for block {section} {letter}"
            )
        cid = block_chunk_id(resource_id, section, letter)
        if cid in block_ids:
            raise ValueError(f"{resource_id}: duplicate block id {cid}")
        block_ids.add(cid)
        text = build_block_text(
            section=section,
            letter=letter,
            title=block.title or "",
            steps=steps,
        )
        instructional.append(
            InstructionalChunk(
                chunk_id=cid,
                resource_id=resource_id,
                text=text,
                content_hash=_sha256_text(text),
                section=section,
                letter=letter,
                title=block.title or "",
                page=block.page if block.page else None,
                minutes=block.minutes,
                steps=steps,
                metadata={
                    "grade": lesson.grade,
                    "module": lesson.module,
                    "unit": lesson.unit,
                    "lesson": lesson.lesson,
                    "family": "instructional",
                    "section": section,
                    "letter": letter,
                },
            )
        )

    pointers: list[EvidencePointer] = []
    for i, item in enumerate(norm.evidence):
        loc = (item.location or "").strip()
        parsed = _parse_location(loc)
        if parsed is None:
            raise ValueError(
                f"{resource_id}: evidence[{i}] location {loc!r} is not "
                f"'{{section}} {{letter}}'"
            )
        section, letter = validate_block_identity(resource_id, parsed[0], parsed[1])
        bid = block_chunk_id(resource_id, section, letter)
        if bid not in block_ids:
            raise ValueError(
                f"{resource_id}: evidence[{i}] location {loc!r} does not join "
                f"any Stage-1 block (resolved {bid!r})"
            )
        quote = (item.quote or "").strip()
        if not quote:
            raise ValueError(f"{resource_id}: evidence[{i}] has empty quote")
        pointers.append(
            EvidencePointer(
                chunk_id=evidence_pointer_id(resource_id, i),
                resource_id=resource_id,
                text="",
                content_hash=_sha256_text(quote),
                block_chunk_id=bid,
                location=loc,
                quote=quote,
                actor=item.actor,
                evidence_role=item.evidence_role,
                support=item.support,
                supports_action=list(item.supports_action),
                qualifiers=list(item.qualifiers),
                evidence_index=i,
                metadata={
                    "block_chunk_id": bid,
                    "location": loc,
                    "actor": item.actor,
                    "evidence_role": item.evidence_role,
                },
            )
        )

    return LessonChunkBundle(
        resource_id=resource_id,
        grade=lesson.grade,
        module=lesson.module,
        unit=lesson.unit,
        lesson=lesson.lesson,
        title=lesson.title,
        prompt_version=norm.prompt_version,
        lesson_chunk=lesson_chunk,
        instructional_chunks=instructional,
        evidence_pointers=pointers,
    )


def chunk_lessons_dir(
    lessons_dir: Path | str,
    normalize_dir: Path | str,
    out_dir: Path | str,
    *,
    force: bool = False,
    resource_ids: set[str] | None = None,
) -> dict:
    """Chunk Stage-1 + normalize lessons into ``out_dir``.

    **Incremental (default):** skip a lesson when ``by_lesson/{code}.json`` already
    exists with a matching ``source_fingerprint`` (Stage-1 + normalize + schema).

    **Maintenance (``force=True``):** rebuild every selected lesson.
    """
    src = Path(lessons_dir)
    norm_dir = Path(normalize_dir)
    dst = Path(out_dir)
    by_lesson = dst / "by_lesson"
    by_lesson.mkdir(parents=True, exist_ok=True)

    lesson_files = iter_lesson_json_files(src)
    if resource_ids is not None:
        lesson_files = [p for p in lesson_files if p.stem in resource_ids]

    progress = {
        "schema_version": CHUNK_SCHEMA_VERSION,
        "mode": "force" if force else "incremental",
        "total": len(lesson_files),
        "completed": [],
        "skipped": [],
        "failed": [],
        "status": "running",
        "lesson_chunks": 0,
        "instructional_chunks": 0,
        "evidence_pointers": 0,
    }

    bundles: list[LessonChunkBundle] = []
    failed: list[dict] = []
    skipped: list[str] = []

    for path in lesson_files:
        code_hint = path.stem
        try:
            stage1_text = path.read_text(encoding="utf-8")
            lesson = Lesson.model_validate_json(stage1_text)
            code_hint = lesson.code
            if resource_ids is not None and lesson.code not in resource_ids:
                continue
            norm_path = norm_dir / f"{safe_code_filename(lesson.code)}.json"
            if not norm_path.is_file():
                raise FileNotFoundError(f"normalize record missing: {norm_path}")
            norm_text = norm_path.read_text(encoding="utf-8")
            fp = source_fingerprint(stage1_text, norm_text)
            out_path = by_lesson / f"{safe_code_filename(lesson.code)}.json"

            if not force and out_path.is_file():
                try:
                    existing = json.loads(out_path.read_text(encoding="utf-8"))
                except json.JSONDecodeError:
                    existing = {}
                if (
                    isinstance(existing, dict)
                    and existing.get("source_fingerprint") == fp
                    and existing.get("schema_version") == CHUNK_SCHEMA_VERSION
                ):
                    bundle = LessonChunkBundle.model_validate(existing)
                    bundles.append(bundle)
                    skipped.append(lesson.code)
                    progress["skipped"].append(lesson.code)
                    progress["completed"].append(lesson.code)
                    progress["lesson_chunks"] += 1
                    progress["instructional_chunks"] += len(bundle.instructional_chunks)
                    progress["evidence_pointers"] += len(bundle.evidence_pointers)
                    print(f"{lesson.code}: SKIP (unchanged fingerprint)", flush=True)
                    continue

            norm = parse_ela_record(norm_text)
            bundle = build_lesson_bundle(lesson, norm).model_copy(
                update={"source_fingerprint": fp}
            )
            atomic_write_text(out_path, dump_bundle_json(bundle))
            bundles.append(bundle)
            progress["completed"].append(lesson.code)
            progress["lesson_chunks"] += 1
            progress["instructional_chunks"] += len(bundle.instructional_chunks)
            progress["evidence_pointers"] += len(bundle.evidence_pointers)
            print(
                f"{lesson.code}: lesson=1 blocks={len(bundle.instructional_chunks)} "
                f"evidence={len(bundle.evidence_pointers)}",
                flush=True,
            )
        except (
            OSError,
            ValueError,
            TypeError,
            json.JSONDecodeError,
            ValidationError,
        ) as e:
            failed.append({"code": code_hint, "error": str(e)})
            progress["failed"].append({"code": code_hint, "error": str(e)})
            print(f"ERROR {code_hint}: {e}", flush=True)

    if resource_ids is not None and not bundles and not failed:
        raise ChunkBuildError(
            f"no lessons matched resource_ids={sorted(resource_ids)} under {src}"
        )

    manifest = {
        "schema_version": CHUNK_SCHEMA_VERSION,
        "mode": "force" if force else "incremental",
        "lessons": len(bundles),
        "built": len(bundles) - len(skipped),
        "skipped": skipped,
        "lesson_chunks": progress["lesson_chunks"],
        "instructional_chunks": progress["instructional_chunks"],
        "evidence_pointers": progress["evidence_pointers"],
        "failed": failed,
        "sections_policy": "stage1_labels",
        "known_el_sections_example": sorted(KNOWN_EL_SECTIONS),
        "outputs": {
            "by_lesson": "by_lesson/",
            "manifest": MANIFEST_NAME,
        },
        "strategy": {
            "lesson": "normalize competency text (1 chunk / lesson)",
            "instructional": (
                "Stage-1 block raw steps (1 chunk / section+letter); "
                "section labels are publisher-agnostic from Stage-1"
            ),
            "evidence_pointer": "join metadata; string-match quote inside block",
            "incremental": (
                "skip when source_fingerprint matches existing bundle "
                "(unless --force)"
            ),
        },
    }
    atomic_write_text(dst / MANIFEST_NAME, json.dumps(manifest, indent=2) + "\n")
    progress["status"] = "complete" if not failed else "partial"
    atomic_write_text(dst / PROGRESS_NAME, json.dumps(progress, indent=2) + "\n")

    print(
        f"Done. lessons={len(bundles)} built={len(bundles) - len(skipped)} "
        f"skipped={len(skipped)} blocks={progress['instructional_chunks']} "
        f"evidence={progress['evidence_pointers']} failed={len(failed)} -> {dst}/",
        flush=True,
    )
    if failed:
        codes = [f["code"] for f in failed]
        preview = codes[:5]
        more = "" if len(codes) <= 5 else f" (+{len(codes) - 5} more)"
        raise ChunkBuildError(
            f"{len(failed)} lesson(s) failed to chunk: {preview}{more} -- "
            f"see {dst}/{PROGRESS_NAME} for details"
        )
    return manifest


__all__ = [
    "CANONICAL_SECTIONS",
    "ChunkBuildError",
    "KNOWN_EL_SECTIONS",
    "PROGRESS_NAME",
    "MANIFEST_NAME",
    "block_chunk_id",
    "build_lesson_bundle",
    "build_lesson_text",
    "build_block_text",
    "chunk_lessons_dir",
    "evidence_pointer_id",
    "lesson_chunk_id",
    "normalize_section_label",
    "source_fingerprint",
    "validate_block_identity",
]

