"""ELA curriculum normalization (Stage 3) — standards-agnostic pedagogy records."""

from .lesson import normalize_lesson, normalize_lessons_dir, lesson_normalize_payload
from .models import (
    ElaLlmDraft,
    NormalizedLesson,
    dump_ela_record,
    dump_ela_record_json,
    minimal_normalized_lesson,
    parse_ela_record,
)

__all__ = [
    "ElaLlmDraft",
    "NormalizedLesson",
    "dump_ela_record",
    "dump_ela_record_json",
    "minimal_normalized_lesson",
    "parse_ela_record",
    "normalize_lesson",
    "normalize_lessons_dir",
    "lesson_normalize_payload",
]
