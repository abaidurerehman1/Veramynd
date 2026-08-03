"""The safety-net verifier.

No lesson set is trusted until it passes these checks. They are organized in three
layers with two severities:

  * FAIL  — a structural violation. The result is BLOCK; do not store the document.
  * WARN  — a plausible anomaly. The result can still be GO, but the item is flagged
            for review.

Layer 1  Separation integrity   (FAIL) — count, coverage, order, spans, ids, contiguity
Layer 2  Cross-signal           (FAIL) — running header agrees with the bookmark code
Layer 3  Division completeness  (WARN) — required blocks present, agenda time in band

The verifier is a pure function of a parsed ``TeacherGuide`` plus (optionally) the
source document for the cross-signal check. It never mutates its input.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from ..config import Config
from ..models import TeacherGuide
from ..pdf.document import PdfDocument
from .. import text_utils as tu


class Severity(str, Enum):
    FAIL = "FAIL"   # blocks the load
    WARN = "WARN"   # flags for review


class Status(str, Enum):
    PASS = "PASS"
    WARN = "WARN"
    FAIL = "FAIL"


@dataclass
class Check:
    name: str
    status: Status
    severity: Severity
    detail: str = ""

    @property
    def ok(self) -> bool:
        return self.status is not Status.FAIL


@dataclass
class VerificationReport:
    checks: list[Check] = field(default_factory=list)

    def add(self, name: str, passed: bool, severity: Severity, detail: str = "") -> None:
        if passed:
            status = Status.PASS
        else:
            status = Status.FAIL if severity is Severity.FAIL else Status.WARN
        self.checks.append(Check(name, status, severity, detail))

    @property
    def fails(self) -> list[Check]:
        return [c for c in self.checks if c.status is Status.FAIL]

    @property
    def warns(self) -> list[Check]:
        return [c for c in self.checks if c.status is Status.WARN]

    @property
    def passed(self) -> bool:
        """True when nothing FAILed — warnings do not block."""
        return not self.fails

    @property
    def verdict(self) -> str:
        return "GO" if self.passed else "BLOCK"

    def render(self) -> str:
        # show the check's severity as its gating role, so a passing hard check
        # reads "PASS  hard" rather than the alarming "PASS  FAIL".
        role = {Severity.FAIL: "hard", Severity.WARN: "soft"}
        lines = [f"{'check':<52}{'result':<7}{'gate':<6}detail",
                 "-" * 86]
        for c in self.checks:
            lines.append(f"{c.name:<52}{c.status.value:<7}{role[c.severity]:<6}{c.detail}")
        lines.append("-" * 86)
        lines.append(
            f"RESULT: {len(self.checks)} checks · {len(self.fails)} FAIL · "
            f"{len(self.warns)} WARN → {self.verdict}"
        )
        return "\n".join(lines)


def _derive_expected_lesson_count(doc: PdfDocument) -> int | None:
    """An expected-count signal independent of the bookmark path that built ``guide``.

    Scans every page's raw text for the running header ('Unit N: Lesson N') and
    counts unique (unit, lesson) pairs across the *whole* document. A lesson whose
    bookmark was dropped, duplicated, or otherwise mishandled by the separation
    path still prints its own running header on its own pages, so this signal
    disagrees with the bookmark-derived lesson count exactly when it should --
    without it, V1 only ever ran when a caller remembered to pass --expect, so a
    silently merged/missing lesson could pass with a clean partition (see V2) and
    no expected-count check at all.
    """
    seen: set[tuple[int, int]] = set()
    for page in range(1, doc.page_count + 1):
        m = tu.RUNNING_HEADER.search(doc.page_text(page))
        if m:
            # groups: grade?, module?, unit, lesson
            seen.add((int(m.group(3)), int(m.group(4))))
    return len(seen) if seen else None


def verify(
    guide: TeacherGuide,
    doc: PdfDocument | None = None,
    cfg: Config | None = None,
    expected_count: int | None = None,
) -> VerificationReport:
    """Run the full safety-net battery against a parsed teacher guide.

    ``doc`` enables the Layer-2 cross-signal check (comparing the running header on
    each lesson's first page to its bookmark code) and, when ``expected_count`` is
    not supplied, an automatically-derived expected count (see
    ``_derive_expected_lesson_count``) so V1 is not silently skipped by default.
    ``expected_count`` overrides the derived value with a known lesson count.
    """
    cfg = cfg or Config()
    rep = VerificationReport()
    lessons = guide.lessons
    n = len(lessons)

    # ---- Layer 0: fallback disclosure (WARN) -------------------------------- #
    # Surfaces reasons that would otherwise be caught-and-discarded exceptions
    # (see pdf/teacher_guide.py) so a fallback that recovered cleanly is still
    # visible in the persisted report, not only in transient CLI stdout.
    if guide.separation_fallback_reason:
        rep.add("V0 separation used the font/header fallback", False, Severity.WARN,
                guide.separation_fallback_reason)
    if guide.engine_fallback_reason:
        rep.add("V0 content engine used a fallback for part of the document", False,
                Severity.WARN, guide.engine_fallback_reason)

    # ---- Layer 1: separation integrity (FAIL) ------------------------------ #
    derived_count = False
    if expected_count is None and doc is not None:
        expected_count = _derive_expected_lesson_count(doc)
        derived_count = expected_count is not None
    if expected_count is not None:
        detail = f"{n} (expected {expected_count}"
        detail += ", derived from running headers)" if derived_count else ")"
        rep.add("V1 lesson count matches expected", n == expected_count,
                Severity.FAIL, detail)

    # coverage: lessons + overviews partition every page with no gap/overlap.
    # Every segment (each unit's overview AND each lesson) is checked against the
    # pages already covered by every *other* segment seen so far — including
    # other overviews — so two unit overviews that both claim the same pages
    # (a separator bug) are caught here too, not just lesson-vs-lesson overlap.
    segments: list[tuple[int, int]] = [
        (unit.overview_page_start, unit.overview_page_end)
        for unit in guide.units
        if unit.overview_page_start and unit.overview_page_end
    ]
    segments += [(lesson.page_start, lesson.page_end) for lesson in lessons]

    covered: set[int] = set()
    overlap = False
    for start, end in segments:
        rng = set(range(start, end + 1))
        if covered & rng:
            overlap = True
        covered |= rng
    full = covered == set(range(1, guide.page_count + 1))
    rep.add("V2 pages fully partition (no gap/overlap)", full and not overlap,
            Severity.FAIL, f"{len(covered)}/{guide.page_count} pages")

    starts = [lesson.page_start for lesson in lessons]
    rep.add("V3 lesson starts strictly increasing",
            starts == sorted(starts) and len(set(starts)) == len(starts), Severity.FAIL)

    rep.add("V4 no inverted page spans",
            all(lesson.page_end >= lesson.page_start for lesson in lessons), Severity.FAIL)

    rep.add("V5 lesson ids unique",
            len({lesson.code for lesson in lessons}) == n, Severity.FAIL)

    contiguous = True
    for unit in guide.units:
        ls = unit.lessons
        for a, b in zip(ls, ls[1:]):
            if a.page_end + 1 != b.page_start:
                contiguous = False
    rep.add("V6 lessons contiguous within each unit", contiguous, Severity.FAIL)

    # ---- Layer 2: cross-signal confirmation (FAIL) ------------------------- #
    if doc is not None:
        confirmed = 0
        mismatched: list[str] = []
        for lesson in lessons:
            m = tu.RUNNING_HEADER.search(doc.page_text(lesson.page_start))
            if m and (int(m.group(3)), int(m.group(4))) == (lesson.unit, lesson.lesson):
                confirmed += 1
            else:
                mismatched.append(lesson.code)
        rep.add("V7 running header matches bookmark code", not mismatched,
                Severity.FAIL,
                f"{confirmed}/{n} confirmed" + (f"; off: {mismatched[:3]}" if mismatched else ""))

    # ---- Layer 3: division completeness (WARN) ----------------------------- #
    missing: list[str] = []
    for lesson in lessons:
        present = {b.section for b in lesson.instructional_blocks}
        need = set(cfg.required_sections)
        if not need <= present:
            missing.append(f"{lesson.code}:{sorted(need - present)}")
    rep.add("V8 every lesson has required blocks", not missing, Severity.WARN,
            f"{len(missing)} missing" if missing else "all present")

    # plan vs execution: every agenda-derived block must have actually been located
    # in the body (page != 0 means its title was found and matched during division).
    # NOTE: len(agenda) == len(instructional_blocks) always holds — both dividers build
    # the block list as a 1:1 comprehension over agenda() — so a count comparison here
    # can never fail. The real signal that division lost a block is an unmatched page.
    plan_mismatch: list[str] = []
    empty_steps: list[str] = []
    for lesson in lessons:
        unmatched = [f"{b.section}/{b.letter}" for b in lesson.instructional_blocks if b.page == 0]
        if unmatched:
            plan_mismatch.append(f"{lesson.code}:{unmatched}")
        if any(not b.steps for b in lesson.instructional_blocks):
            empty_steps.append(lesson.code)
    rep.add("V13 agenda plan matches body blocks", not plan_mismatch, Severity.FAIL,
            ", ".join(plan_mismatch) if plan_mismatch else "all aligned")
    rep.add("V14 every instructional block has steps", not empty_steps, Severity.WARN,
            f"{len(empty_steps)} with an empty block: {empty_steps[:3]}" if empty_steps else "all have steps")

    off_band: list[str] = []
    for lesson in lessons:
        total = lesson.total_minutes
        if total is not None and not (cfg.agenda_min_minutes <= total <= cfg.agenda_max_minutes):
            off_band.append(f"{lesson.code}={total}")
    rep.add("V9 agenda time within sane band", not off_band, Severity.WARN,
            ", ".join(off_band) if off_band else "all in band")

    # completeness of the list sections — every lesson prints Materials and
    # Vocabulary, so an empty one means content was dropped (the gap that a
    # structure-only check does not see).
    no_materials = [l.code for l in lessons if not l.materials]
    rep.add("V11 every lesson has Materials", not no_materials, Severity.FAIL,
            f"{len(no_materials)} empty: {no_materials[:3]}" if no_materials else "all present")
    no_vocab = [l.code for l in lessons if not l.vocabulary]
    rep.add("V12 every lesson has Vocabulary", not no_vocab, Severity.WARN,
            f"{len(no_vocab)} empty: {no_vocab[:3]}" if no_vocab else "all present")

    # ---- Layer 4: cross-engine agreement (FAIL) ---------------------------- #
    # Run only for Docling-parsed lessons. PyMuPDF-fallback lessons are skipped
    # individually — they must not disable V10/V15 for healthy Docling lessons.
    docling_lessons = [l for l in lessons if l.parsed_by == "docling"]
    skipped_pymupdf = [l.code for l in lessons if l.parsed_by != "docling"]

    if doc is not None and docling_lessons:
        ungrounded: list[str] = []
        for lesson in docling_lessons:
            raw = tu.normalize_block(doc.text_range(lesson.page_start, lesson.page_end))
            for code in lesson.declared_standards:
                if code not in raw:
                    ungrounded.append(f"{lesson.code}:{code}")
        detail = (
            f"{len(ungrounded)} ungrounded: {ungrounded[:3]}"
            if ungrounded
            else f"all {len(docling_lessons)} Docling lesson(s) confirmed by second engine"
        )
        if skipped_pymupdf:
            detail += f"; skipped non-Docling: {skipped_pymupdf[:3]}"
        rep.add(
            "V10 Docling standards grounded in PyMuPDF text",
            not ungrounded,
            Severity.FAIL,
            detail,
        )

    # Opt-in V15: re-divide Docling lessons once (shared span map) and compare.
    if cfg.cross_engine_structural_check and doc is not None and docling_lessons:
        from ..pdf.divider import divide as divide_pymupdf
        from ..pdf.separator import SeparationError, separate

        try:
            spans = separate(doc)
        except SeparationError as e:
            rep.add(
                "V15 cross-engine structural agreement (opt-in)",
                False,
                Severity.FAIL,
                f"skipped: outline separation failed ({e})",
            )
            spans = None

        if spans is not None:
            # Build the PyMuPDF re-division once per unique code (P2).
            needed = {lesson.code for lesson in docling_lessons}
            by_code = {
                span.code: divide_pymupdf(doc, span, cfg)
                for span in spans
                if span.code in needed
            }
            mismatched: list[str] = []
            for lesson in docling_lessons:
                other = by_code.get(lesson.code)
                if other is None:
                    mismatched.append(f"{lesson.code}:no-pymupdf-match")
                    continue
                agree = (
                    lesson.page_start == other.page_start
                    and lesson.page_end == other.page_end
                    and set(lesson.declared_standards) == set(other.declared_standards)
                    and lesson.total_minutes == other.total_minutes
                    and [(a.section, a.letter, a.minutes) for a in lesson.agenda]
                    == [(a.section, a.letter, a.minutes) for a in other.agenda]
                    and {b.section for b in lesson.instructional_blocks}
                    == {b.section for b in other.instructional_blocks}
                    and len(lesson.instructional_blocks) == len(other.instructional_blocks)
                )
                if not agree:
                    mismatched.append(lesson.code)
            detail = (
                f"{len(mismatched)} mismatched: {mismatched[:3]}"
                if mismatched
                else (
                    f"{len(by_code)} Docling lesson(s) confirmed by independent "
                    f"PyMuPDF re-division"
                )
            )
            if skipped_pymupdf:
                detail += f"; skipped non-Docling: {skipped_pymupdf[:3]}"
            rep.add(
                "V15 cross-engine structural agreement (opt-in)",
                not mismatched,
                Severity.FAIL,
                detail,
            )

    return rep
