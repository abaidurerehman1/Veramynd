"""Verifier tests — the safety net passes on the real document and blocks on bad input."""

from __future__ import annotations

import copy
from unittest.mock import patch

from veramynd_parser.config import Config
from veramynd_parser.models import AgendaItem, InstructionalBlock, Lesson, TeacherGuide, Unit
from veramynd_parser.pdf.document import PdfDocument
from veramynd_parser.pdf.separator import LessonSpan
from veramynd_parser.verify.verifier import Status, verify


class _FakeDoc:
    """Minimal doc double for verify()'s doc-dependent checks.

    page_count is required by _derive_expected_lesson_count (V1's auto-derived
    expected-count signal, which runs whenever doc is not None) — without it,
    every V15 test using this fixture errors before reaching the check under
    test.
    """

    page_count = 1

    def page_text(self, page: int) -> str:
        return ""

    def text_range(self, start: int, end: int) -> str:
        return ""


class _FakeDocWithHeaders:
    """Doc double whose page_text carries a specific running header per page,
    for testing the V1 (auto-derived expected count) and V7 (cross-signal)
    checks in isolation from a real PDF."""

    def __init__(self, page_count: int, headers: dict[int, str]):
        self.page_count = page_count
        self._headers = headers

    def page_text(self, page: int) -> str:
        return self._headers.get(page, "")

    def text_range(self, start: int, end: int) -> str:
        return " ".join(self._headers.get(p, "") for p in range(start, end + 1))


def test_real_guide_passes_all_hard_checks(guide, guide_path):
    with PdfDocument(guide_path) as doc:
        report = verify(guide, doc=doc, cfg=Config(), expected_count=40)
    assert report.passed
    assert report.verdict == "GO"
    assert report.fails == []


def test_only_expected_warnings_on_real_guide(guide, guide_path):
    with PdfDocument(guide_path) as doc:
        report = verify(guide, doc=doc, cfg=Config(), expected_count=40)
    assert report.passed  # GO — no hard failures
    # the only permissible warning is Vocabulary N/A on the application lessons
    assert all(c.name.startswith("V12") for c in report.warns), [c.name for c in report.warns]


def test_materials_completeness_is_checked(guide, guide_path):
    """A lesson with dropped Materials must FAIL — the check that was missing."""
    import copy

    with PdfDocument(guide_path) as doc:
        broken = copy.deepcopy(guide)
        broken.units[0].lessons[0].materials = []
        report = verify(broken, doc=doc, cfg=Config(), expected_count=40)
    assert not report.passed
    assert any(c.name.startswith("V11") and not c.ok for c in report.checks)


def test_wrong_expected_count_blocks(guide, guide_path):
    with PdfDocument(guide_path) as doc:
        report = verify(guide, doc=doc, cfg=Config(), expected_count=39)
    assert not report.passed
    assert report.verdict == "BLOCK"


def test_inverted_span_is_caught(guide):
    """A corrupted lesson span must fail the integrity layer, not slip through."""
    broken = copy.deepcopy(guide)
    lesson = broken.units[0].lessons[0]
    lesson.page_end = lesson.page_start - 5  # inverted
    report = verify(broken, doc=None, cfg=Config())
    assert not report.passed
    names = [c.name for c in report.fails]
    assert any("inverted" in n or "partition" in n for n in names)


def test_duplicate_id_is_caught(guide):
    broken = copy.deepcopy(guide)
    broken.units[0].lessons[1].code = broken.units[0].lessons[0].code
    report = verify(broken, doc=None, cfg=Config())
    assert not report.passed
    assert any(c.name.startswith("V5") and c.status is Status.FAIL for c in report.checks)


def _synthetic_lesson(*, block_page: int) -> Lesson:
    return Lesson(
        code="G1M2U1L1",
        grade=1,
        module=2,
        unit=1,
        lesson=1,
        title="Lesson 1",
        page_start=1,
        page_end=1,
        declared_standards=["W.1.8"],
        agenda=[AgendaItem(section="Opening", letter="A", title="X", minutes=10)],
        instructional_blocks=[
            InstructionalBlock(
                section="Opening", letter="A", title="X", page=block_page, steps=["did something"]
            ),
        ],
        materials=["paper"],
        vocabulary=["term"],
    )


def _synthetic_guide(lesson: Lesson) -> TeacherGuide:
    return TeacherGuide(
        source_id="test.pdf",
        grade=1,
        module=2,
        page_count=1,
        units=[Unit(unit=1, lessons=[lesson])],
    )


def test_v0_surfaces_fallback_reasons_instead_of_hiding_them():
    """Regression target: a fallback reason used to be a caught-and-discarded
    exception, visible only in transient CLI stdout at parse time (if at all).
    verify() must surface it as a WARN in the persisted VerificationReport too,
    so `export`'s verification_report.txt always shows why a fallback fired."""
    lesson = _synthetic_lesson(block_page=1)
    guide = _synthetic_guide(lesson).model_copy(
        update={
            "separation_fallback_reason": "test.pdf: PDF has no outline/bookmarks",
            "engine_fallback_reason": "G1M2U1L1: Docling division failed (RuntimeError: boom)",
        }
    )
    report = verify(guide, doc=None, cfg=Config())
    v0_names = [c for c in report.checks if c.name.startswith("V0")]
    assert len(v0_names) == 2
    assert all(c.status is Status.WARN for c in v0_names)
    details = [c.detail for c in v0_names]
    assert any("no outline/bookmarks" in d for d in details)
    assert any("Docling division failed" in d for d in details)
    # Fallback disclosures are WARN, not FAIL -- a recovered fallback is still GO.
    assert report.passed


def test_v7_catches_running_header_bookmark_mismatch():
    """Layer-2 cross-signal: the bookmark says G1M2U1L1, but the page's own
    running header says Lesson 2 — must FAIL even though V1 (count) and V2
    (partition) both see a single, cleanly-bounded lesson."""
    guide = _synthetic_guide(_synthetic_lesson(block_page=1))
    doc = _FakeDocWithHeaders(1, {1: "Unit 1: Lesson 2"})
    report = verify(guide, doc=doc, cfg=Config())
    v7 = next(c for c in report.checks if c.name.startswith("V7"))
    assert v7.status is Status.FAIL
    assert "G1M2U1L1" in v7.detail


def test_v1_auto_derives_expected_count_and_catches_a_merged_lesson():
    """Regression target: a missing/merged lesson bookmark used to go undetected
    unless the caller manually passed --expect. V1 now auto-derives its own
    expected count from running headers across the whole document whenever `doc`
    is supplied (see _derive_expected_lesson_count) -- so a document whose
    bookmarks recovered only ONE lesson, but whose running headers show TWO
    distinct (unit, lesson) pairs across that lesson's page span (exactly what a
    dropped/merged bookmark produces), fails V1 with no --expect needed."""
    merged = Lesson(
        code="G1M2U1L1", grade=1, module=2, unit=1, lesson=1, title="Lesson 1",
        page_start=1, page_end=2, declared_standards=["W.1.8"],
        agenda=[AgendaItem(section="Opening", letter="A", title="X", minutes=10)],
        instructional_blocks=[
            InstructionalBlock(section="Opening", letter="A", title="X", page=1, steps=["did something"]),
        ],
        materials=["paper"], vocabulary=["term"],
    )
    guide = TeacherGuide(
        source_id="test.pdf", grade=1, module=2, page_count=2,
        units=[Unit(unit=1, lessons=[merged])],
    )
    doc = _FakeDocWithHeaders(2, {1: "Unit 1: Lesson 1", 2: "Unit 1: Lesson 2"})
    report = verify(guide, doc=doc, cfg=Config())  # no expected_count passed
    v1 = next(c for c in report.checks if c.name.startswith("V1"))
    assert v1.status is Status.FAIL
    assert "derived from running headers" in v1.detail


def test_v13_flags_a_block_never_matched_in_the_body():
    """V13 must FAIL when a block's body position was never located (page stays 0
    from its InstructionalBlock(..., page=0) placeholder) — not merely when the
    agenda/body counts differ, which cannot happen: both dividers build
    instructional_blocks as a 1:1 comprehension over agenda(), so a count mismatch
    can never occur and a check for it alone would never fire.

    Unmatched blocks are a hard production gate: they corrupt step attribution
    under an otherwise GO-looking parse.
    """
    report = verify(_synthetic_guide(_synthetic_lesson(block_page=0)), doc=None, cfg=Config())
    v13 = next(c for c in report.checks if c.name.startswith("V13"))
    assert v13.status is Status.FAIL
    assert "Opening/A" in v13.detail


def test_v13_passes_when_every_block_was_matched():
    report = verify(_synthetic_guide(_synthetic_lesson(block_page=1)), doc=None, cfg=Config())
    v13 = next(c for c in report.checks if c.name.startswith("V13"))
    assert v13.status is Status.PASS


def _v15_report(*, on: bool, doc, other_lesson):
    guide = _synthetic_guide(_synthetic_lesson(block_page=1))
    span = LessonSpan(code="G1M2U1L1", grade=1, module=2, unit=1, lesson=1, page_start=1, page_end=1)
    with patch("veramynd_parser.pdf.separator.separate", return_value=[span]), \
         patch("veramynd_parser.pdf.divider.divide", return_value=other_lesson):
        return verify(guide, doc=doc, cfg=Config(cross_engine_structural_check=on))


def test_v15_absent_when_flag_is_off_by_default():
    report = _v15_report(on=False, doc=_FakeDoc(), other_lesson=_synthetic_lesson(block_page=1))
    assert not any(c.name.startswith("V15") for c in report.checks)


def test_v15_absent_when_flag_on_but_no_doc():
    guide = _synthetic_guide(_synthetic_lesson(block_page=1))
    report = verify(guide, doc=None, cfg=Config(cross_engine_structural_check=True))
    assert not any(c.name.startswith("V15") for c in report.checks)


def test_v15_passes_when_pymupdf_reparse_agrees():
    matching = _synthetic_lesson(block_page=1)  # identical structure
    report = _v15_report(on=True, doc=_FakeDoc(), other_lesson=matching)
    v15 = next(c for c in report.checks if c.name.startswith("V15"))
    assert v15.status is Status.PASS


def test_v15_fails_when_pymupdf_reparse_disagrees():
    """Regression target: this is the runtime check issue #1 in the architecture
    review said was missing — the strongest cross-engine signal only existed as a
    dev-time test, never as something verify() could actually gate on."""
    disagreeing = _synthetic_lesson(block_page=1)
    disagreeing.agenda[0].minutes = 99  # PyMuPDF saw different agenda timing
    report = _v15_report(on=True, doc=_FakeDoc(), other_lesson=disagreeing)
    v15 = next(c for c in report.checks if c.name.startswith("V15"))
    assert v15.status is Status.FAIL
    assert "G1M2U1L1" in v15.detail
