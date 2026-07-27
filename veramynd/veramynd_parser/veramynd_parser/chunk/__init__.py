"""Hierarchical chunking for Stage-1 lessons + ELA normalize records."""

from .builder import (
    CANONICAL_SECTIONS,
    block_chunk_id,
    build_lesson_bundle,
    chunk_lessons_dir,
    lesson_chunk_id,
)
from .models import (
    CHUNK_SCHEMA_VERSION,
    EvidencePointer,
    InstructionalChunk,
    LessonChunk,
    LessonChunkBundle,
)

__all__ = [
    "CANONICAL_SECTIONS",
    "CHUNK_SCHEMA_VERSION",
    "EvidencePointer",
    "InstructionalChunk",
    "LessonChunk",
    "LessonChunkBundle",
    "block_chunk_id",
    "build_lesson_bundle",
    "chunk_lessons_dir",
    "lesson_chunk_id",
]
