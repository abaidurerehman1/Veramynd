"""Load lesson raw text, retrieve candidates, and standard raw_text for the judge."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class JudgeIoError(ValueError):
    pass


def load_json(path: Path | str) -> dict[str, Any]:
    p = Path(path)
    if not p.is_file():
        raise JudgeIoError(f"file not found: {p}")
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise JudgeIoError(f"{p}: invalid JSON ({e})") from e
    if not isinstance(data, dict):
        raise JudgeIoError(f"{p}: expected JSON object")
    return data


def lesson_raw_text_from_stage1(lesson: dict[str, Any]) -> str:
    """Join instructional block steps (judge + grounding lane)."""
    parts: list[str] = []
    title = (lesson.get("title") or "").strip()
    if title:
        parts.append(title)
    targets = lesson.get("learning_targets") or []
    for t in targets:
        if isinstance(t, dict):
            text = (t.get("text") or "").strip()
        else:
            text = str(t).strip()
        if text:
            parts.append(f"Learning target: {text}")
    blocks = lesson.get("instructional_blocks") or []
    for b in blocks:
        if not isinstance(b, dict):
            continue
        section = (b.get("section") or "").strip()
        letter = (b.get("letter") or "").strip()
        btitle = (b.get("title") or "").strip()
        page = b.get("page")
        header = f"[{section} {letter}] {btitle}".strip()
        if page is not None:
            header = f"{header} (page {page})"
        parts.append(header)
        for step in b.get("steps") or []:
            s = str(step).strip()
            if s:
                parts.append(f"- {s}")
    text = "\n".join(parts).strip()
    if not text:
        raise JudgeIoError("lesson has no instructional steps for judge grounding")
    return text


def lesson_raw_text_from_chunks(bundle: dict[str, Any]) -> str:
    """Prefer instructional chunk texts/steps from a by_lesson chunk bundle."""
    parts: list[str] = []
    title = (bundle.get("title") or "").strip()
    if title:
        parts.append(title)
    for ch in bundle.get("instructional_chunks") or []:
        if not isinstance(ch, dict):
            continue
        text = (ch.get("text") or "").strip()
        if text:
            parts.append(text)
            continue
        for step in ch.get("steps") or []:
            s = str(step).strip()
            if s:
                parts.append(f"- {s}")
    text = "\n".join(parts).strip()
    if not text:
        raise JudgeIoError("chunk bundle has no instructional text for judge grounding")
    return text


def load_lesson_context(
    *,
    lesson_file: Path | str | None = None,
    chunk_file: Path | str | None = None,
) -> tuple[str, str, str]:
    """Return ``(resource_id, lesson_raw_text, source_label)``."""
    if lesson_file:
        data = load_json(lesson_file)
        rid = str(
            data.get("code") or data.get("resource_id") or Path(lesson_file).stem
        ).strip()
        return rid, lesson_raw_text_from_stage1(data), f"stage1:{rid}"
    if chunk_file:
        data = load_json(chunk_file)
        rid = str(
            data.get("resource_id") or data.get("code") or Path(chunk_file).stem
        ).strip()
        return rid, lesson_raw_text_from_chunks(data), f"chunks:{rid}"
    raise JudgeIoError("provide --lesson-file or --chunk-file for raw lesson text")


def load_retrieve_document(retrieve_file: Path | str) -> dict[str, Any]:
    data = load_json(retrieve_file)
    cands = data.get("candidates")
    if not isinstance(cands, list) or not cands:
        raise JudgeIoError(f"{retrieve_file}: no candidates[] to judge")
    return data


def candidates_from_retrieve_document(data: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for c in data.get("candidates") or []:
        if not isinstance(c, dict):
            continue
        code = (c.get("standard_code") or "").strip()
        if code:
            out.append(c)
    if not out:
        raise JudgeIoError("candidates missing standard_code")
    return out


def load_retrieve_candidates(retrieve_file: Path | str) -> list[dict[str, Any]]:
    return candidates_from_retrieve_document(load_retrieve_document(retrieve_file))


def load_standard_raw_text(standards_dir: Path | str, code: str) -> dict[str, Any]:
    """Load normalized standard leaf; prefer ``raw_text`` for the judge."""
    from ..normalize.standard import safe_standard_filename

    try:
        safe = safe_standard_filename(code)
    except ValueError as e:
        raise JudgeIoError(str(e)) from e
    root = Path(standards_dir).resolve()
    path = (root / f"{safe}.json").resolve()
    if not path.is_relative_to(root):
        raise JudgeIoError(f"unsafe standard code for use as a filename: {code!r}")
    if not path.is_file():
        raise JudgeIoError(f"standard not found: {path}")
    data = load_json(path)
    raw = (data.get("raw_text") or data.get("competency_statement") or "").strip()
    if not raw:
        raise JudgeIoError(f"{path}: empty raw_text")
    return {
        "standard_code": (data.get("standard_code") or code).strip(),
        "raw_text": raw,
        "competency_statement": (data.get("competency_statement") or "").strip(),
        "domain_primary": (
            (domain.get("primary") or "").strip()
            if isinstance(domain := data.get("domain"), dict)
            else ""
        ),
        "label": (data.get("label") or "").strip(),
        "level": (data.get("level") or "").strip(),
        "grade": data.get("grade"),
        "skill_clauses": data.get("skill_clauses") or [],
    }


__all__ = [
    "JudgeIoError",
    "lesson_raw_text_from_chunks",
    "lesson_raw_text_from_stage1",
    "candidates_from_retrieve_document",
    "load_json",
    "load_lesson_context",
    "load_retrieve_candidates",
    "load_retrieve_document",
    "load_standard_raw_text",
]
