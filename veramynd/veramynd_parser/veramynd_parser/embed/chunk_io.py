"""Load embeddable chunks from hierarchical by_lesson bundles."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class EmbeddableChunk:
    chunk_id: str
    family: str
    resource_id: str
    text: str
    content_hash: str
    metadata: dict[str, Any] = field(default_factory=dict)


_EMBED_FAMILIES = frozenset({"lesson", "instructional"})


def load_embeddable_chunks(chunks_dir: Path | str) -> list[EmbeddableChunk]:
    """Read ``by_lesson/*.json`` and return lesson + instructional chunks only."""
    root = Path(chunks_dir)
    by_lesson = root / "by_lesson"
    if not by_lesson.is_dir():
        raise FileNotFoundError(f"missing by_lesson/ under {root}")

    out: list[EmbeddableChunk] = []
    seen: set[str] = set()
    files = sorted(by_lesson.glob("*.json"))
    if not files:
        raise FileNotFoundError(f"no lesson bundles in {by_lesson}")

    for path in files:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            raise ValueError(f"{path}: invalid JSON ({e})") from e

        resource_id = (data.get("resource_id") or "").strip()
        if not resource_id:
            raise ValueError(f"{path}: missing resource_id")

        rows: list[dict] = []
        lesson = data.get("lesson_chunk")
        if isinstance(lesson, dict):
            rows.append(lesson)
        for block in data.get("instructional_chunks") or []:
            if isinstance(block, dict):
                rows.append(block)

        for row in rows:
            family = (row.get("family") or "").strip()
            if family not in _EMBED_FAMILIES:
                raise ValueError(
                    f"{path}: unexpected family {family!r} on chunk "
                    f"{row.get('chunk_id')!r}; expected lesson|instructional"
                )
            chunk_id = (row.get("chunk_id") or "").strip()
            text = (row.get("text") or "").strip()
            if not chunk_id:
                raise ValueError(f"{path}: chunk missing chunk_id")
            if not text:
                raise ValueError(f"{path}: empty text for {chunk_id}")
            if chunk_id in seen:
                raise ValueError(f"duplicate chunk_id across bundles: {chunk_id}")
            seen.add(chunk_id)
            rid = (row.get("resource_id") or resource_id).strip()
            if rid != resource_id:
                raise ValueError(
                    f"{path}: chunk {chunk_id} resource_id {rid!r} "
                    f"!= bundle {resource_id!r}"
                )
            out.append(
                EmbeddableChunk(
                    chunk_id=chunk_id,
                    family=family,
                    resource_id=rid,
                    text=text,
                    content_hash=(row.get("content_hash") or "").strip(),
                    metadata=dict(row.get("metadata") or {}),
                )
            )
    return out


__all__ = ["EmbeddableChunk", "load_embeddable_chunks"]
