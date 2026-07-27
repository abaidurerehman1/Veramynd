"""Lesson separation — where each lesson begins and ends.

Strategy: the teacher guide ships with a complete PDF outline in which every lesson
is one bookmark coded ``G1M2U1L1`` (grade / module / unit / lesson). We read those
bookmarks and turn them into half-open page spans. Unit-overview bookmarks are held
out — they are not lessons.

If a future document has no usable outline, ``separate_by_font`` recovers lesson
starts from the running header. Both paths always emit full ``G#M#U#L#`` codes and
raise when grade/module cannot be determined.
"""

from __future__ import annotations

from dataclasses import dataclass

from .. import text_utils as tu
from .document import OutlineEntry, PdfDocument


@dataclass(frozen=True)
class LessonSpan:
    """A lesson's identity and page boundaries, before its content is parsed."""

    code: str
    grade: int
    module: int
    unit: int
    lesson: int
    page_start: int
    page_end: int


@dataclass(frozen=True)
class Segment:
    """A top-level document segment (a lesson or a unit overview)."""

    title: str
    page_start: int
    page_end: int
    is_lesson: bool


def _top_level(outline: list[OutlineEntry]) -> list[OutlineEntry]:
    """Keep only the outline's shallowest-depth entries."""
    if not outline:
        return outline
    top = min(e.level for e in outline)
    return [e for e in outline if e.level == top]


def _segments(outline: list[OutlineEntry], page_count: int) -> list[Segment]:
    """Turn consecutive outline entries into contiguous, non-overlapping segments."""
    outline = _top_level(outline)
    segs: list[Segment] = []
    for i, entry in enumerate(outline):
        end = outline[i + 1].page - 1 if i + 1 < len(outline) else page_count
        segs.append(
            Segment(
                title=entry.title,
                page_start=entry.page,
                page_end=end,
                is_lesson=tu.parse_lesson_code(entry.title) is not None,
            )
        )
    return segs


def _make_span(
    *,
    grade: int,
    module: int,
    unit: int,
    lesson: int,
    page_start: int,
    page_end: int,
    source_id: str,
) -> LessonSpan:
    if grade < 1 or module < 1:
        raise SeparationError(
            f"{source_id}: cannot build lesson id with grade={grade} module={module} "
            f"(unit={unit} lesson={lesson}) — grade and module must be >= 1"
        )
    if unit < 1 or lesson < 1:
        raise SeparationError(
            f"{source_id}: cannot build lesson id with unit={unit} lesson={lesson} "
            f"— both must be >= 1"
        )
    if page_end < page_start:
        raise SeparationError(
            f"{source_id}: inverted page span {page_start}-{page_end} for "
            f"G{grade}M{module}U{unit}L{lesson}"
        )
    return LessonSpan(
        code=f"G{grade}M{module}U{unit}L{lesson}",
        grade=grade,
        module=module,
        unit=unit,
        lesson=lesson,
        page_start=page_start,
        page_end=page_end,
    )


def separate(doc: PdfDocument) -> list[LessonSpan]:
    """Separate a teacher guide into lesson spans using its PDF outline.

    Raises ``SeparationError`` if the document has no outline, or if the outline
    yields zero lesson bookmarks.
    """
    outline = doc.outline()
    if not outline:
        raise SeparationError(f"{doc.source_id}: PDF has no outline/bookmarks")

    spans: list[LessonSpan] = []
    for seg in _segments(outline, doc.page_count):
        parsed = tu.parse_lesson_code(seg.title)
        if parsed is None:
            continue  # unit overview or other non-lesson bookmark — held out
        if seg.page_end < seg.page_start:
            raise SeparationError(
                f"{doc.source_id}: lesson bookmark '{seg.title}' has an inverted "
                f"page span ({seg.page_start}-{seg.page_end}) — likely duplicate or "
                f"out-of-order bookmarks in the PDF outline"
            )
        g, m, u, l = parsed
        spans.append(
            _make_span(
                grade=g,
                module=m,
                unit=u,
                lesson=l,
                page_start=seg.page_start,
                page_end=seg.page_end,
                source_id=doc.source_id,
            )
        )

    if not spans:
        raise SeparationError(
            f"{doc.source_id}: PDF outline has no lesson-code bookmarks "
            f"(expected titles like G1M2U1L1) — found {len(outline)} outline entries"
        )
    return spans


def overview_spans(doc: PdfDocument) -> list[Segment]:
    """The non-lesson (unit overview) segments — useful for coverage checks."""
    outline = doc.outline()
    return [s for s in _segments(outline, doc.page_count) if not s.is_lesson]


def synthesize_overview_spans(
    spans: list[LessonSpan], page_count: int
) -> list[Segment]:
    """Recover overview page ranges when the PDF outline has no overview bookmarks.

    Font/header separation yields lesson spans only. Unit overviews sit in the
    gaps (before the first lesson, and between the last lesson of unit N and the
    first lesson of unit N+1). Without these segments, verifier V2 always FAILs
    the full-page partition even when lessons themselves are correct.
    """
    if not spans or page_count < 1:
        return []
    ordered = sorted(spans, key=lambda s: s.page_start)
    overviews: list[Segment] = []

    # Pages before the first lesson.
    first = ordered[0]
    if first.page_start > 1:
        overviews.append(
            Segment(
                title=f"U{first.unit} Overview",
                page_start=1,
                page_end=first.page_start - 1,
                is_lesson=False,
            )
        )

    # Gaps between consecutive lessons (typically unit divider / overview pages).
    for prev, nxt in zip(ordered, ordered[1:]):
        gap_start = prev.page_end + 1
        gap_end = nxt.page_start - 1
        if gap_start <= gap_end:
            # Attribute the gap to the upcoming unit (publisher places overview
            # cards immediately before that unit's lessons).
            overviews.append(
                Segment(
                    title=f"U{nxt.unit} Overview",
                    page_start=gap_start,
                    page_end=gap_end,
                    is_lesson=False,
                )
            )

    # Pages after the last lesson (rare; still needed for V2 full coverage).
    last = ordered[-1]
    if last.page_end < page_count:
        overviews.append(
            Segment(
                title=f"U{last.unit} Overview",
                page_start=last.page_end + 1,
                page_end=page_count,
                is_lesson=False,
            )
        )
    return overviews


def _header_identity(text: str) -> tuple[int, int, int, int] | None:
    """Parse grade/module/unit/lesson from a page's running header text."""
    m = tu.RUNNING_HEADER.search(text)
    if not m:
        return None
    grade_s, module_s, unit_s, lesson_s = m.groups()
    if not grade_s or not module_s:
        return None
    return int(grade_s), int(module_s), int(unit_s), int(lesson_s)


def separate_by_font(doc: PdfDocument) -> list[LessonSpan]:
    """Fallback separation for documents without a usable outline.

    Requires a full running header that includes Grade and Module
    (``Grade N: Module N: Unit N: Lesson N``). Never emits ``U#L#`` or grade/module 0.
    """
    starts: list[tuple[int, int, int, int, int]] = []  # page, g, m, u, l
    seen: set[tuple[int, int, int, int]] = set()
    partial_headers = 0

    for page in range(1, doc.page_count + 1):
        text = doc.page_text(page)
        m = tu.RUNNING_HEADER.search(text)
        if not m:
            continue
        grade_s, module_s, unit_s, lesson_s = m.groups()
        if not grade_s or not module_s:
            partial_headers += 1
            continue
        identity = (int(grade_s), int(module_s), int(unit_s), int(lesson_s))
        if identity not in seen:
            seen.add(identity)
            starts.append((page, *identity))

    if not starts:
        detail = (
            f" ({partial_headers} page(s) had Unit/Lesson without Grade/Module)"
            if partial_headers
            else ""
        )
        raise SeparationError(
            f"{doc.source_id}: font/header separation found zero lessons — need "
            f"running headers like 'Grade N: Module N: Unit N: Lesson N'{detail}"
        )

    spans: list[LessonSpan] = []
    for i, (page, grade, module, unit, lesson) in enumerate(starts):
        end = starts[i + 1][0] - 1 if i + 1 < len(starts) else doc.page_count
        spans.append(
            _make_span(
                grade=grade,
                module=module,
                unit=unit,
                lesson=lesson,
                page_start=page,
                page_end=end,
                source_id=doc.source_id,
            )
        )
    return spans


class SeparationError(RuntimeError):
    """Raised when a document cannot be separated by the requested strategy."""
