"""Unit tests for separator.py's bookmark handling — nested outlines and
missing/malformed outlines — that don't need a real PDF or Docling.

Regression targets:
  * Nested PDF bookmarks (e.g. a lesson bookmark with child bookmarks for its own
    Opening/Work Time sub-sections) must not corrupt lesson boundaries — only the
    outline's shallowest-depth entries are genuine document-level boundaries.
  * A malformed outline (inverted/duplicate bookmark pages) must raise a clear,
    reportable SeparationError, not fail silently or with an opaque traceback.
"""

from __future__ import annotations

import pytest

from veramynd_parser.pdf.document import OutlineEntry
from veramynd_parser.pdf.separator import (
    LessonSpan,
    SeparationError,
    _segments,
    _top_level,
    separate,
    synthesize_overview_spans,
)


def test_top_level_keeps_only_shallowest_depth_entries():
    outline = [
        OutlineEntry(level=1, title="G1M2U1L1", page=1),
        OutlineEntry(level=2, title="Opening", page=1),  # nested child bookmark
        OutlineEntry(level=2, title="Work Time", page=3),  # nested child bookmark
        OutlineEntry(level=1, title="G1M2U1L2", page=6),
    ]
    top = _top_level(outline)
    assert [e.title for e in top] == ["G1M2U1L1", "G1M2U1L2"]


def test_top_level_empty_outline():
    assert _top_level([]) == []


def test_segments_boundaries_unaffected_by_nested_child_bookmarks():
    """A child bookmark's page must never end the PREVIOUS top-level entry's span
    early -- that's exactly the silent-truncation bug filtering to top-level depth
    fixes. Lesson 1 (with children at pages 1 and 3) must still span pages 1-5,
    not get truncated to 1-2 by its own 'Work Time' child at page 3."""
    outline = [
        OutlineEntry(level=1, title="G1M2U1L1", page=1),
        OutlineEntry(level=2, title="Opening", page=1),
        OutlineEntry(level=2, title="Work Time", page=3),
        OutlineEntry(level=1, title="G1M2U1L2", page=6),
    ]
    segs = _segments(outline, page_count=10)
    assert len(segs) == 2
    l1, l2 = segs
    assert (l1.title, l1.page_start, l1.page_end) == ("G1M2U1L1", 1, 5)
    assert (l2.title, l2.page_start, l2.page_end) == ("G1M2U1L2", 6, 10)


class _FakeOutlineDoc:
    """Doc double exposing only what separate() needs: outline() and page_count."""

    def __init__(self, outline: list[OutlineEntry], page_count: int, source_id: str = "test.pdf"):
        self._outline = outline
        self.page_count = page_count
        self.source_id = source_id

    def outline(self) -> list[OutlineEntry]:
        return self._outline


def test_separate_end_to_end_ignores_nested_bookmarks():
    outline = [
        OutlineEntry(level=1, title="G1M2U1L1", page=1),
        OutlineEntry(level=2, title="Opening", page=1),
        OutlineEntry(level=2, title="Work Time", page=3),
        OutlineEntry(level=1, title="G1M2U1L2", page=6),
    ]
    spans = separate(_FakeOutlineDoc(outline, page_count=10))
    assert [s.code for s in spans] == ["G1M2U1L1", "G1M2U1L2"]
    assert (spans[0].page_start, spans[0].page_end) == (1, 5)
    assert (spans[1].page_start, spans[1].page_end) == (6, 10)


def test_separate_raises_on_no_outline():
    with pytest.raises(SeparationError, match="no outline"):
        separate(_FakeOutlineDoc([], page_count=10))


def test_separate_raises_when_outline_has_no_lesson_bookmarks():
    outline = [
        OutlineEntry(level=1, title="Unit 1 Overview", page=1),
        OutlineEntry(level=1, title="Unit 2 Overview", page=5),
    ]
    with pytest.raises(SeparationError, match="no lesson-code bookmarks"):
        separate(_FakeOutlineDoc(outline, page_count=10))


def test_separate_raises_clear_error_on_inverted_bookmark_span():
    """A duplicate/out-of-order bookmark must surface a specific, actionable
    SeparationError (caught upstream in pdf/teacher_guide.py and recorded on
    TeacherGuide.separation_fallback_reason -- see test_teacher_guide_fallback.py),
    not fail silently or with an unrelated traceback."""
    outline = [
        OutlineEntry(level=1, title="G1M2U1L1", page=5),
        OutlineEntry(level=1, title="G1M2U1L2", page=1),  # out of order
    ]
    with pytest.raises(SeparationError, match="inverted page span"):
        separate(_FakeOutlineDoc(outline, page_count=10))


def test_synthesize_overview_spans_fills_gaps_between_units():
    """Font-fallback separation has no outline overviews; gaps must still be
    covered so verifier V2 can GO."""
    spans = [
        LessonSpan("G1M2U1L1", 1, 2, 1, 1, 5, 10),
        LessonSpan("G1M2U1L2", 1, 2, 1, 2, 11, 15),
        LessonSpan("G1M2U2L1", 1, 2, 2, 1, 20, 25),
    ]
    overs = synthesize_overview_spans(spans, page_count=30)
    assert overs[0].page_start == 1 and overs[0].page_end == 4
    # gap between U1L2 and U2L1
    mid = [o for o in overs if o.page_start == 16 and o.page_end == 19]
    assert mid and "U2" in mid[0].title
    assert overs[-1].page_start == 26 and overs[-1].page_end == 30
