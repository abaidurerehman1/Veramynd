"""Build retrieval/embed text for alignable (leaf) standards."""

from __future__ import annotations

from typing import Any


def build_retrieval_text(data: dict[str, Any]) -> str:
    """Rich leaf text for BM25, rerank, and dense embed (enterprise K-12).

    Uses competency, skills, behaviors, pedagogy terms, and student actions —
    not parent-folder summaries. Falls back to ``embed_text`` / ``raw_text``.
    """
    parts: list[str] = []
    code = (data.get("standard_code") or "").strip()
    if code:
        parts.append(f"Standard: {code}")
    label = (data.get("label") or "").strip()
    if label:
        parts.append(f"Label: {label}")
    domain = data.get("domain") or {}
    if isinstance(domain, dict):
        primary = (domain.get("primary") or "").strip()
        if primary:
            parts.append(f"Domain primary: {primary}")
        secondary = [
            str(x).strip()
            for x in (domain.get("secondary") or [])
            if str(x).strip()
        ]
        if secondary:
            parts.append(f"Domain secondary: {', '.join(secondary)}")
    competency = (data.get("competency_statement") or "").strip()
    if competency:
        parts.append(f"Competency: {competency}")
    raw = (data.get("raw_text") or "").strip()
    if raw and raw != competency:
        parts.append(f"Official text: {raw}")
    skills = [str(x).strip() for x in (data.get("skill_clauses") or []) if str(x).strip()]
    if skills:
        parts.append("Skills:")
        parts.extend(f"- {s}" for s in skills)
    behaviors = [
        str(x).strip()
        for x in (data.get("observable_behaviors") or [])
        if str(x).strip()
    ]
    if behaviors:
        parts.append("Observable behaviors:")
        parts.extend(f"- {b}" for b in behaviors)
    terms = [
        str(x).strip() for x in (data.get("pedagogy_terms") or []) if str(x).strip()
    ]
    if terms:
        parts.append("Pedagogy terms / keywords: " + ", ".join(terms))
    actions = data.get("student_actions") or {}
    if isinstance(actions, dict):
        action_lines = []
        for key, val in actions.items():
            if key == "domain_specific" or not isinstance(val, str):
                continue
            v = val.strip()
            if v and v.upper() != "NONE OBSERVED":
                action_lines.append(f"- {key}: {v}")
        if action_lines:
            parts.append("Required student actions:")
            parts.extend(action_lines)
    text = "\n".join(parts).strip()
    embed = (data.get("embed_text") or "").strip()
    if embed:
        if not text:
            return embed
        if embed not in text:
            return f"{text}\n{embed}"
    if text:
        return text
    return (data.get("raw_text") or "").strip()


__all__ = ["build_retrieval_text"]
