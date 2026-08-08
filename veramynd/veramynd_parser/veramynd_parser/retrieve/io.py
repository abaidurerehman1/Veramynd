"""Load standard docs + lesson query text for hybrid retrieval."""

from __future__ import annotations

import json
from pathlib import Path

from ..embed.standard_io import load_embeddable_standards
from .models import StandardDoc


def load_standard_docs(
    standards_dir: Path | str,
    *,
    leaves_only: bool = True,
) -> list[StandardDoc]:
    """Load normalized standards for BM25 / hybrid fusion.

    Default ``leaves_only=True`` keeps terminal (alignable) codes only —
    parent folders are excluded from the retrieve funnel.

    Document ``text`` matches dense embed text (rich leaf representation).
    """
    rows = load_embeddable_standards(
        standards_dir,
        leaves_only=leaves_only,
        use_rich_text=True,
    )
    return [
        StandardDoc(
            standard_code=r.standard_code,
            text=r.text,
            domain_primary=r.domain_primary,
            parent_code=str(r.metadata.get("parent_code") or ""),
            label=r.label,
            level=r.level,
            grade=r.grade,
            metadata=dict(r.metadata),
        )
        for r in rows
    ]



def lesson_query_from_chunk_bundle(
    path: Path | str,
    *,
    family: str = "lesson",
) -> tuple[str, str]:
    """Return ``(query_text, source_label)`` from a by_lesson chunk JSON."""
    p = Path(path)
    data = json.loads(p.read_text(encoding="utf-8"))
    if family == "lesson":
        row = data.get("lesson_chunk") or {}
        text = (row.get("text") or "").strip()
        label = (row.get("chunk_id") or p.name).strip()
        if not text:
            raise ValueError(f"{p}: empty lesson_chunk.text")
        return text, label

    blocks = data.get("instructional_chunks") or []
    if not blocks:
        raise ValueError(f"{p}: no instructional_chunks")
    # Use first instructional block in document order — no phonics-biased pick.
    chosen = blocks[0]
    text = (chosen.get("text") or "").strip()
    label = (chosen.get("chunk_id") or p.name).strip()
    if not text:
        raise ValueError(f"{p}: empty instructional chunk text")
    return text, label


def instructional_queries_from_chunk_bundle(
    path: Path | str,
) -> list[tuple[str, str]]:
    """Return ``[(query_text, chunk_id), ...]`` for each instructional chunk.

    Falls back to the single lesson-level chunk when instructional sections
    are missing (keeps retrieve runnable on older bundles).
    """
    p = Path(path)
    data = json.loads(p.read_text(encoding="utf-8"))
    out: list[tuple[str, str]] = []
    for block in data.get("instructional_chunks") or []:
        if not isinstance(block, dict):
            continue
        text = (block.get("text") or "").strip()
        if not text:
            continue
        label = (block.get("chunk_id") or "").strip() or f"{p.stem}#instructional"
        out.append((text, label))
    if out:
        return out
    # Fallback: whole-lesson query.
    text, label = lesson_query_from_chunk_bundle(p, family="lesson")
    return [(text, label)]


def rerank_query_from_chunk_bundle(path: Path | str) -> str:
    """Lesson-level text for cross-encoder rerank (broader context than one section)."""
    text, _ = lesson_query_from_chunk_bundle(path, family="lesson")
    return text


def lesson_query_from_normalize(path: Path | str) -> tuple[str, str]:
    """Build a retrieval query from a NormalizedLesson JSON (competency view)."""
    p = Path(path)
    data = json.loads(p.read_text(encoding="utf-8"))
    rid = (data.get("resource_id") or p.stem).strip()
    domain = data.get("domain") or {}
    primary = (domain.get("primary") or "").strip() if isinstance(domain, dict) else ""
    secondary = []
    if isinstance(domain, dict):
        secondary = [str(x).strip() for x in (domain.get("secondary") or []) if str(x).strip()]
    objective = (data.get("objective") or "").strip()
    skills = []
    for item in data.get("what_is_taught") or []:
        if isinstance(item, dict) and (item.get("skill") or "").strip():
            skills.append(item["skill"].strip())
    actions = data.get("student_actions") or {}
    action_lines = []
    if isinstance(actions, dict):
        for key, val in actions.items():
            if key == "domain_specific":
                continue
            v = (val or "").strip() if isinstance(val, str) else ""
            if v and v.upper() != "NONE OBSERVED":
                action_lines.append(f"{key}: {v}")
    lines = [
        f"Domain primary: {primary or 'unknown'}",
        f"Domain secondary: {', '.join(secondary) if secondary else 'none'}",
        f"Objective: {objective}" if objective else "",
        "Skills taught:",
        *[f"- {s}" for s in skills],
        "Student actions:",
        *[f"- {a}" for a in action_lines],
    ]
    text = "\n".join(x for x in lines if x).strip()
    if not text:
        raise ValueError(f"{p}: could not build query from normalize record")
    return text, rid


__all__ = [
    "instructional_queries_from_chunk_bundle",
    "lesson_query_from_chunk_bundle",
    "lesson_query_from_normalize",
    "load_standard_docs",
    "rerank_query_from_chunk_bundle",
]
