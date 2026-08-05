"""Focused multi-intent lesson queries for enterprise K-12 retrieval.

Curriculum-agnostic: reads common normalized lesson fields (objective, skills,
student/teacher actions, vocabulary, evidence) without publisher-specific IDs.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def _clean(s: Any) -> str:
    return " ".join(str(s or "").split()).strip()


def _action_lines(actions: Any, *, limit: int = 8) -> list[str]:
    if not isinstance(actions, dict):
        return []
    out: list[str] = []
    for key, val in actions.items():
        if key == "domain_specific":
            continue
        if isinstance(val, dict):
            continue
        text = _clean(val)
        if not text or text.upper() == "NONE OBSERVED":
            continue
        out.append(f"{key}: {text}")
        if len(out) >= limit:
            break
    return out


def focused_queries_from_normalize(
    path: Path | str,
    *,
    max_queries: int = 12,
    max_evidence: int = 4,
) -> list[dict[str, str]]:
    """Build focused retrieval queries from a NormalizedLesson JSON.

    Each item is ``{"query_id", "source", "text"}``. Deduplicates near-identical
    texts. Returns at least one query when any usable field exists.
    """
    p = Path(path)
    data = json.loads(p.read_text(encoding="utf-8"))
    rid = _clean(data.get("resource_id") or p.stem) or p.stem
    queries: list[dict[str, str]] = []

    def add(source: str, text: str) -> None:
        t = _clean(text)
        if len(t) < 12:
            return
        if any(_clean(q["text"]).lower() == t.lower() for q in queries):
            return
        queries.append(
            {
                "query_id": f"{rid}#{source}#{len(queries)+1}",
                "source": source,
                "text": t,
            }
        )

    objective = _clean(data.get("objective"))
    if objective:
        add("objective", f"Lesson objective: {objective}")

    domain = data.get("domain") or {}
    if isinstance(domain, dict):
        primary = _clean(domain.get("primary"))
        secondary = [
            _clean(x)
            for x in (domain.get("secondary") or [])
            if _clean(x)
        ]
        if primary:
            bits = [f"Domain primary: {primary}"]
            if secondary:
                bits.append(f"Domain secondary: {', '.join(secondary)}")
            add("domain", " | ".join(bits))

    skills: list[str] = []
    for item in data.get("what_is_taught") or []:
        if isinstance(item, dict):
            skill = _clean(item.get("skill"))
            if skill:
                skills.append(skill)
        elif isinstance(item, str) and _clean(item):
            skills.append(_clean(item))
    for i, skill in enumerate(skills[:6], start=1):
        add(f"skill_{i}", f"Students learn / practice: {skill}")

    for line in _action_lines(data.get("student_actions")):
        add("student_action", f"Student action — {line}")

    for line in _action_lines(data.get("teacher_actions"), limit=6):
        add("teacher_action", f"Teacher action — {line}")

    vocab = data.get("vocabulary") or {}
    if isinstance(vocab, dict):
        new_v = [_clean(x) for x in (vocab.get("new") or []) if _clean(x)]
        review_v = [_clean(x) for x in (vocab.get("review") or []) if _clean(x)]
        words = new_v + review_v
        if words:
            add(
                "vocabulary",
                "Vocabulary targets: " + "; ".join(words[:12]),
            )

    evidence_bits: list[str] = []
    for item in data.get("evidence") or []:
        if not isinstance(item, dict):
            continue
        quote = _clean(item.get("quote") or item.get("text"))
        if quote:
            evidence_bits.append(quote)
        if len(evidence_bits) >= max_evidence:
            break
    for i, quote in enumerate(evidence_bits, start=1):
        # Keep evidence queries bounded — long quotes dilute embeddings.
        add(f"evidence_{i}", f"Classroom evidence / prompt: {quote[:500]}")

    protocols = data.get("protocols_routines") or []
    if isinstance(protocols, list):
        proto = [_clean(x) for x in protocols if _clean(x)]
        if proto:
            add("protocols", "Protocols / routines: " + "; ".join(proto[:6]))

    assessment = data.get("assessment")
    if isinstance(assessment, dict):
        atext = _clean(
            assessment.get("summary")
            or assessment.get("description")
            or assessment.get("task")
        )
        if atext:
            add("assessment", f"Assessment / task: {atext}")
    elif isinstance(assessment, str) and _clean(assessment):
        add("assessment", f"Assessment / task: {_clean(assessment)}")

    if not queries:
        title = _clean(data.get("title"))
        if title:
            add("title", f"Lesson: {title}")
        elif objective:
            add("objective", objective)
        else:
            raise ValueError(f"{p}: no usable fields for focused retrieval queries")

    return queries[:max_queries]


def rerank_context_from_normalize(path: Path | str, *, max_chars: int = 6000) -> str:
    """Broader lesson context string for cross-encoder rerank."""
    p = Path(path)
    data = json.loads(p.read_text(encoding="utf-8"))
    parts: list[str] = []
    for key in ("title", "objective"):
        val = _clean(data.get(key))
        if val:
            parts.append(f"{key}: {val}")
    domain = data.get("domain") or {}
    if isinstance(domain, dict) and _clean(domain.get("primary")):
        parts.append(f"domain: {_clean(domain.get('primary'))}")
    skills = []
    for item in data.get("what_is_taught") or []:
        if isinstance(item, dict) and _clean(item.get("skill")):
            skills.append(_clean(item["skill"]))
    if skills:
        parts.append("skills: " + "; ".join(skills[:8]))
    for line in _action_lines(data.get("student_actions"), limit=6):
        parts.append(f"student: {line}")
    text = "\n".join(parts).strip()
    if not text:
        raise ValueError(f"{p}: empty rerank context")
    return text[:max_chars]


__all__ = [
    "focused_queries_from_normalize",
    "rerank_context_from_normalize",
]
