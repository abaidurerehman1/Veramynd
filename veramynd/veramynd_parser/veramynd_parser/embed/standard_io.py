"""Load embeddable normalized standards (one vector per alignable leaf)."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .standard_text import build_retrieval_text

# Hierarchy folders are never alignment / embed targets.
_NON_ALIGNABLE_LEVELS = frozenset({"domain", "big_idea"})


@dataclass(frozen=True)
class EmbeddableStandard:
    standard_code: str
    text: str
    content_hash: str
    level: str
    grade: int | None
    framework: str
    label: str
    domain_primary: str
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def point_key(self) -> str:
        """Stable id key for Qdrant point UUID (``std:{code}``)."""
        return f"std:{self.standard_code}"


_SKIP_NAMES = frozenset(
    {
        "normalize_standards_progress.json",
        "normalize_standards_manifest.json",
        "embed_progress.json",
        "embed_manifest.json",
    }
)


def content_hash_for_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _filter_alignable_leaves(
    rows: list[EmbeddableStandard],
) -> list[EmbeddableStandard]:
    """Keep terminal standards only (codes that are not parents of others)."""
    parent_codes: set[str] = set()
    for r in rows:
        raw = ""
        if isinstance(r.metadata, dict):
            raw = (r.metadata.get("parent_code") or "").strip()
        if raw:
            parent_codes.add(raw)
    out: list[EmbeddableStandard] = []
    for r in rows:
        level = (r.level or "").strip().lower()
        if level in _NON_ALIGNABLE_LEVELS:
            continue
        code = (r.standard_code or "").strip()
        if not code or code in parent_codes:
            continue
        out.append(r)
    return out


def load_embeddable_standards(
    standards_dir: Path | str,
    *,
    codes: set[str] | None = None,
    leaves_only: bool = True,
    use_rich_text: bool = True,
) -> list[EmbeddableStandard]:
    """Read ``normalize_standards/*.json`` for dense embed / BM25.

    Enterprise defaults:
    - ``leaves_only=True`` — embed/retrieve terminal codes only (parents stay on disk)
    - ``use_rich_text=True`` — embed competency/skills/verbs/keywords, not a thin sentence

    All files are always parsed and validated (leaf detection needs the full
    corpus to know which codes are parents); when ``codes`` is set, the result
    is filtered to those ``standard_code`` values AFTER leaf filtering — so
    requesting a non-leaf parent fails loud instead of embedding it.
    """
    root = Path(standards_dir)
    if not root.is_dir():
        raise FileNotFoundError(f"standards dir not found: {root}")

    out: list[EmbeddableStandard] = []
    seen: set[str] = set()
    files = sorted(
        p
        for p in root.glob("*.json")
        if p.name not in _SKIP_NAMES and not p.name.startswith("_")
    )
    if not files:
        raise FileNotFoundError(f"no normalized standard JSON under {root}")

    for path in files:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            raise ValueError(f"{path}: invalid JSON ({e})") from e

        if not isinstance(data, dict):
            raise ValueError(f"{path}: expected object")
        # Progress sidecar without standard_code.
        if "standard_code" not in data and "completed" in data:
            continue

        code = (data.get("standard_code") or "").strip()
        if not code:
            raise ValueError(f"{path}: missing standard_code")

        if use_rich_text:
            text = build_retrieval_text(data).strip()
        else:
            text = (data.get("embed_text") or "").strip()
        if not text:
            raise ValueError(f"{path}: empty retrieval/embed text for {code}")

        if code in seen:
            raise ValueError(f"duplicate standard_code across files: {code}")
        seen.add(code)

        domain = data.get("domain") or {}
        domain_primary = ""
        if isinstance(domain, dict):
            domain_primary = (domain.get("primary") or "").strip()

        grade_raw = data.get("grade")
        grade: int | None
        try:
            grade = int(grade_raw) if grade_raw is not None else None
        except (TypeError, ValueError):
            grade = None

        out.append(
            EmbeddableStandard(
                standard_code=code,
                text=text,
                content_hash=content_hash_for_text(text),
                level=(data.get("level") or "").strip(),
                grade=grade,
                framework=(data.get("framework") or "").strip(),
                label=(data.get("label") or "").strip(),
                domain_primary=domain_primary,
                metadata={
                    "parent_code": (data.get("parent_code") or "").strip() or None,
                    "cognitive_demand": (data.get("cognitive_demand") or "").strip()
                    or None,
                    "prompt_version": (data.get("prompt_version") or "").strip() or None,
                    "embed_text_mode": "rich_leaf" if use_rich_text else "embed_text",
                },
            )
        )

    # Leaf-filter over the FULL corpus before any codes subsetting: computing
    # parenthood from a requested subset can't see a parent's children, so
    # ``--code <parent>`` used to embed a non-leaf standard as a "leaf".
    if leaves_only:
        out = _filter_alignable_leaves(out)
    if codes is not None:
        out = [r for r in out if r.standard_code in codes]

    if codes is not None and not out:
        raise FileNotFoundError(
            f"no embeddable standards for codes={sorted(codes)} under {root}"
        )
    if not out:
        raise FileNotFoundError(
            f"no alignable leaf standards under {root} (leaves_only={leaves_only})"
        )
    return out


__all__ = [
    "EmbeddableStandard",
    "content_hash_for_text",
    "load_embeddable_standards",
]
