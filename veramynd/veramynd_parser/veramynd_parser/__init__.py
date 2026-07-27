"""Veramynd document parser.

A structure-aware parser for curriculum documents. It separates a teacher guide into
individual lessons, divides each lesson into its parts, parses a standards
spreadsheet into a grade-indexed tree, and verifies the result with a layered
safety net.

Public API
----------
    parse_teacher_guide(path, cfg)   -> TeacherGuide
    parse_standards(path, framework) -> GradeStandards
    verify(guide, doc, cfg)          -> VerificationReport
"""

from __future__ import annotations

from .config import Config
from .models import (
    AgendaItem,
    GradeStandards,
    LearningTarget,
    Lesson,
    Standard,
    StandardLevel,
    Table,
    TeacherGuide,
    Unit,
)
from .normalize import NormalizedLesson, normalize_lesson, normalize_lessons_dir
from .pdf.teacher_guide import parse_teacher_guide
from .standards.spreadsheet import parse_standards
from .verify.verifier import Severity, Status, VerificationReport, verify

__version__ = "0.1.0"

__all__ = [
    "Config",
    "Lesson",
    "Unit",
    "TeacherGuide",
    "LearningTarget",
    "AgendaItem",
    "Table",
    "Standard",
    "StandardLevel",
    "GradeStandards",
    "NormalizedLesson",
    "parse_teacher_guide",
    "parse_standards",
    "normalize_lesson",
    "normalize_lessons_dir",
    "verify",
    "VerificationReport",
    "Severity",
    "Status",
]
