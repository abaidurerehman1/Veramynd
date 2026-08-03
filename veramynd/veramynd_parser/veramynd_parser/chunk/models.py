"""Production chunk contracts for Stage-1 lessons + ELA normalize records.

Hierarchy:
  - lesson: competency summary from normalize
  - instructional: one chunk per Stage-1 block (section + letter)
  - evidence_pointer: join metadata for quote grounding inside a block
"""

from __future__ import annotations

import json
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

_STRICT = ConfigDict(extra="forbid")

CHUNK_SCHEMA_VERSION = "1.0-chunk"

ChunkFamily = Literal["lesson", "instructional", "evidence_pointer"]
InstructionalSection = Literal["Opening", "Work Time", "Closing and Assessment"]


class ChunkBase(BaseModel):
    model_config = _STRICT

    chunk_id: str
    family: ChunkFamily
    resource_id: str
    text: str = ""
    content_hash: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class LessonChunk(ChunkBase):
    family: Literal["lesson"] = "lesson"


class InstructionalChunk(ChunkBase):
    family: Literal["instructional"] = "instructional"
    section: str
    letter: str
    title: str = ""
    page: int | None = None
    minutes: int | None = None
    steps: list[str] = Field(default_factory=list)


class EvidencePointer(ChunkBase):
    """Grounding join record — quote string-match inside an instructional block."""

    family: Literal["evidence_pointer"] = "evidence_pointer"
    block_chunk_id: str
    location: str
    quote: str
    actor: str = ""
    evidence_role: str = ""
    support: str = ""
    supports_action: list[str] = Field(default_factory=list)
    qualifiers: list[str] = Field(default_factory=list)
    evidence_index: int = 0


class LessonChunkBundle(BaseModel):
    """All chunks for one lesson code."""

    model_config = _STRICT

    schema_version: str = CHUNK_SCHEMA_VERSION
    resource_id: str
    grade: int | None = None
    module: int | None = None
    unit: int | None = None
    lesson: int | None = None
    title: str = ""
    prompt_version: str = ""
    # sha256(schema + stage1 JSON + normalize JSON) — incremental skip key
    source_fingerprint: str = ""
    lesson_chunk: LessonChunk
    instructional_chunks: list[InstructionalChunk] = Field(default_factory=list)
    evidence_pointers: list[EvidencePointer] = Field(default_factory=list)


def dump_bundle(bundle: LessonChunkBundle) -> dict:
    return bundle.model_dump(mode="json")


def dump_bundle_json(bundle: LessonChunkBundle, *, indent: int = 2) -> str:
    return json.dumps(dump_bundle(bundle), indent=indent, ensure_ascii=False) + "\n"


__all__ = [
    "CHUNK_SCHEMA_VERSION",
    "ChunkBase",
    "ChunkFamily",
    "EvidencePointer",
    "InstructionalChunk",
    "InstructionalSection",
    "LessonChunk",
    "LessonChunkBundle",
    "dump_bundle",
    "dump_bundle_json",
]
