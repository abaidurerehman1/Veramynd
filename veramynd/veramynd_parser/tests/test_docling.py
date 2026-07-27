"""Docling-engine tests — the primary path, plus cross-engine agreement.

These exercise the two-engine design directly: Docling extracts the content and
tables; PyMuPDF independently confirms the structural facts. Skipped if Docling is
not installed.
"""

from __future__ import annotations

import importlib.util

import pytest

pytestmark = pytest.mark.skipif(
    importlib.util.find_spec("docling") is None, reason="docling not installed"
)


def test_lessons_report_docling_as_engine(guide):
    assert all(lesson.parsed_by == "docling" for lesson in guide.lessons)


def test_ocr_auto_detection(guide_path):
    """The reference PDF is born-digital, so auto-detect must skip OCR."""
    from veramynd_parser.config import Config
    from veramynd_parser.pdf.docling_parser import _has_text_layer, resolve_ocr

    cfg = Config()
    assert _has_text_layer(guide_path, cfg) is True
    assert resolve_ocr(guide_path, cfg) is False        # auto → no OCR (text layer present)
    assert resolve_ocr(guide_path, Config(ocr_mode="on")) is True   # forced on
    assert resolve_ocr(guide_path, Config(ocr_mode="off")) is False  # forced off


def test_guide_records_ocr_state(guide):
    assert guide.engine == "docling"
    assert guide.ocr_used is False                      # born-digital → OCR not used


def test_only_genuine_tables_are_kept(guide):
    """Every retained table is a real (>=2-column) table, never a 1-column list.

    (This document's lessons contain lists, not data tables, so the count is 0 —
    the point is that a mis-detected 1-column list is never surfaced as a table.)
    """
    for lesson in guide.lessons:
        for table in lesson.tables:
            assert table.n_cols >= 2, f"{lesson.code} kept a 1-column list as a table"
            assert lesson.page_start <= table.page <= lesson.page_end
            assert table.n_rows == len(table.cells)


def test_materials_and_vocabulary_are_captured(guide):
    """The Materials/Vocabulary lists must not be silently dropped (the regression)."""
    for lesson in guide.lessons:
        assert lesson.materials, f"{lesson.code} dropped its Materials list"
    # Vocabulary is present on most lessons; a few application lessons are N/A.
    with_vocab = sum(1 for lesson in guide.lessons if lesson.vocabulary)
    assert with_vocab >= 35


def test_materials_recovered_from_misdetected_table(guide):
    """G1M2U1L1's Materials/Vocabulary were absorbed into a mis-detected 1-col table;
    they must still be recovered by flattening that table back into a list."""
    l1 = next(l for l in guide.lessons if l.code == "G1M2U1L1")
    assert len(l1.materials) >= 10
    assert l1.vocabulary == [
        "sun, moon, stars (L)",
        "Review: observe, effective (L)",
    ]
    assert l1.tables == []            # the 1-col mis-detection is not surfaced as a table


def test_cross_engine_structural_agreement(guide, guide_pymupdf):
    """Both engines must agree on every structural fact — the cross-check that matters.

    (Free text like titles may differ — Docling rejoins hyphenated wraps and keeps
    full multi-line titles — but the structural fields must be identical.)
    """
    dl = {l.code: l for l in guide.lessons}
    pm = {l.code: l for l in guide_pymupdf.lessons}
    assert dl.keys() == pm.keys()
    for code, a in dl.items():
        b = pm[code]
        assert a.page_start == b.page_start and a.page_end == b.page_end, code
        assert set(a.declared_standards) == set(b.declared_standards), code
        assert a.total_minutes == b.total_minutes, code
        assert [(x.section, x.letter, x.minutes) for x in a.agenda] == \
               [(x.section, x.letter, x.minutes) for x in b.agenda], code
        assert {s.section for s in a.instructional_blocks} == \
               {s.section for s in b.instructional_blocks}, code
        # both engines find the same number of sub-blocks
        assert len(a.instructional_blocks) == len(b.instructional_blocks), code


def test_declared_standards_grounded_cross_engine(guide, guide_path):
    """The V10 cross-engine check: PyMuPDF confirms every standard Docling reported."""
    from veramynd_parser.config import Config
    from veramynd_parser.pdf.document import PdfDocument
    from veramynd_parser.verify.verifier import verify

    with PdfDocument(guide_path) as doc:
        report = verify(guide, doc=doc, cfg=Config(), expected_count=40)
    v10 = [c for c in report.checks if c.name.startswith("V10")]
    assert v10 and v10[0].ok
    assert report.passed
