"""parse_teacher_guide's degrade-not-crash fallbacks — separation and content
engine — with the reasons surfaced on the returned TeacherGuide, not discarded.

These patch DoclingParse.parse itself (which is importable without the docling
package installed — docling is only imported lazily inside its own _convert), so
they exercise the real fallback code path in pdf/teacher_guide.py without
requiring the heavy docling dependency.
"""

from __future__ import annotations

from unittest.mock import patch

from veramynd_parser.config import Config
from veramynd_parser.pdf.docling_parser import DoclingParse
from veramynd_parser.pdf.teacher_guide import parse_teacher_guide


def test_docling_failure_falls_back_to_pymupdf_for_whole_document(guide_path):
    """Regression target: if Docling crashes (model download failure, an internal
    error, etc.), parsing must fall back to the PyMuPDF divider for the whole
    document and record why on TeacherGuide.engine_fallback_reason."""
    with (
        patch("veramynd_parser.pdf.teacher_guide._require_docling_installed"),
        patch(
            "veramynd_parser.pdf.docling_parser.DoclingParse.parse",
            side_effect=RuntimeError("simulated Docling model download failure"),
        ),
    ):
        guide = parse_teacher_guide(guide_path, Config(engine="docling"))

    assert guide.lessons  # recovered lessons despite Docling failing
    assert guide.engine_fallback_reason is not None
    assert "Docling parse failed" in guide.engine_fallback_reason
    assert "simulated Docling model download failure" in guide.engine_fallback_reason
    assert all(lesson.parsed_by == "pymupdf" for lesson in guide.lessons)
    assert guide.engine == "pymupdf"  # honest engine after whole-document fallback


def test_engine_is_honest_when_every_lesson_falls_back_individually(guide_path):
    """Regression: the whole-document Docling *parse* can succeed while every
    single lesson's Docling *division* still fails and falls back to PyMuPDF
    individually (a different failure mode than the whole-document parse
    failure covered above). TeacherGuide.engine used to be left at "docling" in
    that case even though zero lessons actually used it -- the same dishonesty
    the whole-document fallback already fixed, just one level down."""
    fake_docling = DoclingParse("test.pdf", elements=[], tables=[])
    with (
        patch("veramynd_parser.pdf.teacher_guide._require_docling_installed"),
        patch(
            "veramynd_parser.pdf.docling_parser.DoclingParse.parse",
            return_value=fake_docling,
        ),
        patch(
            "veramynd_parser.pdf.docling_divider.divide",
            side_effect=RuntimeError("simulated Docling division failure"),
        ),
    ):
        guide = parse_teacher_guide(guide_path, Config(engine="docling"))

    assert guide.lessons
    assert all(lesson.parsed_by == "pymupdf" for lesson in guide.lessons)
    assert guide.engine == "pymupdf"  # honest even though the whole-doc parse succeeded
    assert guide.engine_fallback_reason is not None


def test_pymupdf_engine_leaves_no_fallback_reason(guide_path):
    """Sanity check on the other side of the same field: requesting the PyMuPDF
    engine directly (Docling never attempted at all) must leave
    engine_fallback_reason unset -- it only records an actual Docling failure,
    not merely "Docling wasn't used"."""
    guide = parse_teacher_guide(guide_path, Config(engine="pymupdf"))
    assert guide.engine_fallback_reason is None
