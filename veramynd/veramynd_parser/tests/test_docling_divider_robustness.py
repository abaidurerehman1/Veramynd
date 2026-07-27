"""Docling divider robustness — how it behaves when Docling mislabels an element.

These construct a ``DoclingParse`` directly from hand-written elements (no real PDF
or the ``docling`` package needed), so they can pin down label-inconsistency cases
the reference document doesn't happen to trigger.
"""

from __future__ import annotations

from veramynd_parser.config import Config
from veramynd_parser.pdf.docling_divider import divide
from veramynd_parser.pdf.docling_parser import DoclingParse, Element
from veramynd_parser.pdf.separator import LessonSpan


def _span() -> LessonSpan:
    return LessonSpan(code="G1M2U1L1", grade=1, module=2, unit=1, lesson=1, page_start=1, page_end=1)


def test_agenda_survives_a_lettered_header_mislabeled_as_section_header():
    """Regression: a lettered sub-block header Docling tags as section_header must
    not be mistaken for a real section boundary (e.g. 'Teaching Notes') and end the
    agenda early — that silently dropped every later block from the lesson."""
    elements = [
        Element("section_header", "Lesson 1: Sample Title", 1),
        Element("section_header", "Agenda", 1),
        Element("section_header", "1. Opening", 1),
        Element("list_item", "A. Reading Aloud (10 minutes)", 1),
        Element("section_header", "2. Work Time", 1),
        Element("list_item", "A. Shared Writing (10 minutes)", 1),
        # Docling mislabels this lettered header as a section_header instead of a
        # list_item — the case the old code treated as "agenda is over".
        Element("section_header", "B. Independent Writing (15 minutes)", 1),
        Element("section_header", "3. Closing and Assessment", 1),
        Element("list_item", "A. Debrief (10 minutes)", 1),
        Element("section_header", "Teaching Notes", 1),
    ]
    lesson = divide(DoclingParse("test.pdf", elements, []), _span(), Config())

    assert [(a.section, a.letter, a.title, a.minutes) for a in lesson.agenda] == [
        ("Opening", "A", "Reading Aloud", 10),
        ("Work Time", "A", "Shared Writing", 10),
        ("Work Time", "B", "Independent Writing", 15),
        ("Closing and Assessment", "A", "Debrief", 10),
    ]
    assert len(lesson.instructional_blocks) == 4


def test_agenda_ignores_a_duplicate_agenda_header_mid_scan():
    """Characterization test, not a regression: a stray repeated 'Agenda' header
    mid-scan (re-affirming the same state) must not be mistaken for a genuine
    non-agenda header ending the scan."""
    elements = [
        Element("section_header", "Lesson 1: Sample Title", 1),
        Element("section_header", "Agenda", 1),
        Element("section_header", "1. Opening", 1),
        Element("list_item", "A. Reading Aloud (10 minutes)", 1),
        Element("section_header", "Agenda", 1),  # spurious duplicate
        Element("list_item", "B. Shared Writing (10 minutes)", 1),
    ]
    lesson = divide(DoclingParse("test.pdf", elements, []), _span(), Config())
    assert [(a.section, a.letter) for a in lesson.agenda] == [
        ("Opening", "A"),
        ("Opening", "B"),
    ]


def test_agenda_recovers_a_bare_section_name_mislabeled_as_list_item():
    """Characterization test: 'Opening' printed bare (no leading '1.') and tagged
    list_item instead of section_header must still open a new agenda section."""
    elements = [
        Element("section_header", "Lesson 1: Sample Title", 1),
        Element("section_header", "Agenda", 1),
        Element("list_item", "Opening", 1),
        Element("list_item", "A. Reading Aloud (10 minutes)", 1),
        Element("list_item", "Work Time", 1),
        Element("list_item", "A. Shared Writing (10 minutes)", 1),
    ]
    lesson = divide(DoclingParse("test.pdf", elements, []), _span(), Config())
    assert [(a.section, a.letter) for a in lesson.agenda] == [
        ("Opening", "A"),
        ("Work Time", "A"),
    ]


def test_agenda_ends_at_a_genuine_non_agenda_header():
    """Characterization test: an actual non-agenda header ('Teaching Notes') must
    still end the scan — only lettered/duplicate-Agenda headers are tolerated."""
    elements = [
        Element("section_header", "Lesson 1: Sample Title", 1),
        Element("section_header", "Agenda", 1),
        Element("section_header", "1. Opening", 1),
        Element("list_item", "A. Reading Aloud (10 minutes)", 1),
        Element("section_header", "Teaching Notes", 1),
        Element("list_item", "Some teaching note text.", 1),
    ]
    lesson = divide(DoclingParse("test.pdf", elements, []), _span(), Config())
    assert [(a.section, a.letter) for a in lesson.agenda] == [("Opening", "A")]


def test_agenda_preserves_printed_letter_not_sequential_counter():
    """When Docling surfaces 'B. …' then 'A. …' out of order, keep printed letters."""
    elements = [
        Element("section_header", "Lesson 1: Sample Title", 1),
        Element("section_header", "Agenda", 1),
        Element("section_header", "1. Opening", 1),
        Element("list_item", "B. Second activity (10 minutes)", 1),
        Element("list_item", "A. First activity (10 minutes)", 1),
        Element("section_header", "Teaching Notes", 1),
    ]
    lesson = divide(DoclingParse("test.pdf", elements, []), _span(), Config())
    assert [(a.letter, a.title) for a in lesson.agenda] == [
        ("B", "Second activity"),
        ("A", "First activity"),
    ]


def test_codes_under_stops_at_teaching_notes_even_if_not_section_header():
    elements = [
        Element("section_header", "CCS Standards", 1),
        Element("list_item", "W.1.8", 1),
        Element("list_item", "SL.1.1", 1),
        Element("text", "Teaching Notes", 1),  # mislabeled — must still stop
        Element("list_item", "RF.1.2", 1),  # must NOT be collected
        Element("section_header", "Opening", 1),
    ]
    lesson = divide(DoclingParse("test.pdf", elements, []), _span(), Config())
    assert lesson.declared_standards == ["W.1.8", "SL.1.1"]


def test_vocabulary_excludes_legend_even_when_docling_tags_it_as_plain_text():
    """Regression: 'Key:' and its (L)/(T)/(W) legend must not leak into vocabulary
    when Docling labels them as list_item/text instead of section_header — the old
    code only filtered the legend out via _is_header_text() for mis-detected table
    rows, not for ordinary elements."""
    elements = [
        Element("section_header", "Lesson 1: Sample Title", 1),
        Element("section_header", "Vocabulary", 1),
        Element("list_item", "Key:", 1),
        Element("list_item", "(L): Language, (T): Things, (W): Words", 1),
        Element("section_header", "New:", 1),
        Element("list_item", "sun, moon, stars (L)", 1),
        Element("section_header", "Review:", 1),
        Element("list_item", "observe (L)", 1),
        Element("section_header", "Teaching Notes", 1),
    ]
    lesson = divide(DoclingParse("test.pdf", elements, []), _span(), Config())

    assert lesson.vocabulary == ["sun, moon, stars (L)", "observe (L)"]
