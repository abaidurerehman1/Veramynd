"""Load embeddable normalized standards (one vector per leaf via ``embed_text``)."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


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


def load_embeddable_standards(
    standards_dir: Path | str,
    *,
    codes: set[str] | None = None,
) -> list[EmbeddableStandard]:
    """Read ``normalize_standards/*.json`` leaves; skip progress/manifest sidecars.

    If ``codes`` is set, only those ``standard_code`` values are loaded.
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
        if codes is not None and code not in codes:
            continue

        text = (data.get("embed_text") or "").strip()
        if not text:
            raise ValueError(f"{path}: empty embed_text for {code}")

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
                },
            )
        )

    if codes is not None and not out:
        raise FileNotFoundError(
            f"no embeddable standards for codes={sorted(codes)} under {root}"
        )
    return out


__all__ = [
    "EmbeddableStandard",
    "content_hash_for_text",
    "load_embeddable_standards",
]
