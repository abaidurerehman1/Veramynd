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
from .standard import (
    normalize_standard,
    normalize_standards_tree,
    standard_normalize_payload,
)
from .standard_models import (
    NormalizedStandard,
    StandardLlmDraft,
    build_standard_embed_text,
    dump_normalized_standard_json,
    parse_normalized_standard,
)

__all__ = [
    "ElaLlmDraft",
    "NormalizedLesson",
    "NormalizedStandard",
    "StandardLlmDraft",
    "build_standard_embed_text",
    "dump_ela_record",
    "dump_ela_record_json",
    "dump_normalized_standard_json",
    "minimal_normalized_lesson",
    "parse_ela_record",
    "parse_normalized_standard",
    "normalize_lesson",
    "normalize_lessons_dir",
    "normalize_standard",
    "normalize_standards_tree",
    "lesson_normalize_payload",
    "standard_normalize_payload",
]
