"""Teacher-guide orchestration — separate, divide, assemble.

Ties the PDF stages together into one pure function:

    parse_teacher_guide(path, cfg) -> TeacherGuide

It separates the document into lesson spans, divides each into a structured
``Lesson``, groups them by unit alongside their overviews, and returns the whole
``TeacherGuide`` contract. No verification happens here — that is a separate stage
(``verify``) so that parsing and checking stay independent.
"""

from __future__ import annotations

import importlib.util
import re
import warnings
from pathlib import Path

from ..config import Config
from ..models import TeacherGuide, Unit
from .divider import divide as divide_pymupdf
from .document import PdfDocument
from .separator import (
    LessonSpan,
    SeparationError,
    overview_spans,
    separate,
    separate_by_font,
    synthesize_overview_spans,
)


def _group_units(lessons, overviews) -> list[Unit]:
    """Group lessons by unit, attaching each unit's overview page span if present."""
    overview_by_unit: dict[int, tuple[int, int]] = {}

    for seg in overviews:
        m = re.search(r"U(\d+)", seg.title)
        if m:
            overview_by_unit[int(m.group(1))] = (seg.page_start, seg.page_end)

    units: dict[int, Unit] = {}
    for lesson in lessons:
        unit = units.get(lesson.unit)
        if unit is None:
            ov = overview_by_unit.get(lesson.unit, (None, None))
            unit = Unit(unit=lesson.unit, overview_page_start=ov[0], overview_page_end=ov[1])
            units[lesson.unit] = unit
        unit.lessons.append(lesson)
    return [units[k] for k in sorted(units)]


def _require_docling_installed() -> None:
    """C1: engine=docling must mean Docling is actually installed — no silent downgrade."""
    if importlib.util.find_spec("docling") is None:
        raise RuntimeError(
            "Config.engine is 'docling' but the docling package is not installed. "
            "Install it with: pip install 'veramynd-parser[docling]' "
            "(or pass --engine pymupdf to use the lightweight path explicitly)."
        )


def parse_teacher_guide(path: str | Path, cfg: Config | None = None) -> TeacherGuide:
    """Parse a teacher-guide PDF into a fully structured ``TeacherGuide``.

    Separation is always PyMuPDF-driven (the bookmarks/outline), because Docling does
    not expose them. Division uses the configured engine: ``docling`` (default —
    semantic structure and tables) or ``pymupdf`` (font-tier fallback).

    When ``engine='docling'`` and Docling is not installed, this raises immediately
    (no silent engine downgrade). Runtime Docling failures after a successful import
    may still fall back per-document or per-lesson; those paths record
    ``engine_fallback_reason`` and emit a warning.
    """
    cfg = cfg or Config()
    separation_fallback_reason: str | None = None
    engine_fallback_reason: str | None = None

    if cfg.engine == "docling":
        _require_docling_installed()

    # 1. Separation + the source metadata — always PyMuPDF (reads the outline)
    with PdfDocument(path) as doc:
        try:
            spans: list[LessonSpan] = separate(doc)
        except SeparationError as e:
            separation_fallback_reason = str(e)
            spans = separate_by_font(doc)

        if not spans:
            raise SeparationError(
                f"{doc.source_id}: separation produced zero lessons "
                f"(outline and font/header paths both failed to find lesson starts)"
            )

        # Prefer outline overviews; if missing (common on font-fallback path),
        # synthesize from gaps so V2 can still partition the full document.
        overviews = overview_spans(doc)
        if not overviews:
            overviews = synthesize_overview_spans(spans, doc.page_count)

        source_id = doc.source_id
        page_count = doc.page_count

        # 2. Division — Docling primary, PyMuPDF fallback on runtime failure only
        ocr_used = False
        effective_engine = cfg.engine
        if cfg.engine == "docling":
            from .docling_divider import divide as divide_docling
            from .docling_parser import DoclingParse

            docling = None
            try:
                docling = DoclingParse.parse(path, cfg)
                ocr_used = docling.ocr_used
            except (OSError, RuntimeError, ValueError, ImportError) as e:
                engine_fallback_reason = (
                    f"Docling parse failed ({type(e).__name__}: {e}) — used PyMuPDF "
                    f"for the whole document."
                )
                warnings.warn(engine_fallback_reason, stacklevel=2)
                effective_engine = "pymupdf"

            if docling is not None:
                lessons = []
                for span in spans:
                    try:
                        lessons.append(divide_docling(docling, span, cfg))
                    except (
                        OSError,
                        RuntimeError,
                        ValueError,
                        KeyError,
                        IndexError,
                        # Unexpected Docling object shapes surface as these two
                        # more often than any of the above — without them, one
                        # odd element crashes the whole parse instead of
                        # degrading that lesson to PyMuPDF.
                        AttributeError,
                        TypeError,
                    ) as e:
                        lessons.append(divide_pymupdf(doc, span, cfg))
                        note = (
                            f"{span.code}: Docling division failed "
                            f"({type(e).__name__}: {e}) — used PyMuPDF for this lesson."
                        )
                        warnings.warn(note, stacklevel=2)
                        engine_fallback_reason = (
                            note
                            if engine_fallback_reason is None
                            else f"{engine_fallback_reason} {note}"
                        )
                # The Docling parse succeeded but every single lesson's division
                # fell back to PyMuPDF individually -- `engine="docling"` would
                # otherwise be left standing even though zero lessons actually used
                # it, unlike the whole-document parse-failure branch above (tested
                # as "honest engine after whole-document fallback" in
                # test_teacher_guide_fallback.py), which already corrects this for
                # the coarser failure mode.
                if lessons and all(lesson.parsed_by == "pymupdf" for lesson in lessons):
                    effective_engine = "pymupdf"
                    # OCR belonged to the abandoned Docling parse — claiming it
                    # for an all-PyMuPDF result would be false provenance.
                    ocr_used = False
            else:
                lessons = [divide_pymupdf(doc, span, cfg) for span in spans]
        else:
            lessons = [divide_pymupdf(doc, span, cfg) for span in spans]

    grade = lessons[0].grade if lessons else 0
    module = lessons[0].module if lessons else 0
    return TeacherGuide(
        source_id=source_id,
        grade=grade,
        module=module,
        page_count=page_count,
        engine=effective_engine,
        ocr_used=ocr_used,
        units=_group_units(lessons, overviews),
        separation_fallback_reason=separation_fallback_reason,
        engine_fallback_reason=engine_fallback_reason,
    )
