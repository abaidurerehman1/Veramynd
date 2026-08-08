"""Remap TeacherGuide / Lesson page fields from PDF indices to printed footers.

Internal parsing keeps PDF indices. Call ``for_export`` immediately before
serializing JSON so exports contain **only** printed footer page numbers.
"""

from __future__ import annotations

from pathlib import Path

from ..models import InstructionalBlock, Lesson, Provenance, Table, TeacherGuide, Unit
from .page_map import PageMapError, PrintedPageMap, build_printed_page_map


def for_export(
    guide: TeacherGuide,
    pdf_path: str | Path,
    *,
    page_map: PrintedPageMap | None = None,
) -> TeacherGuide:
    """Return a deep-copied guide with all page fields converted to printed numbers."""
    pmap = page_map or build_printed_page_map(pdf_path)
    units = [_remap_unit(u, pmap) for u in guide.units]
    # page_count stays as PDF page count (document length), not max printed number
    return guide.model_copy(update={"units": units})


def remap_lesson(lesson: Lesson, page_map: PrintedPageMap) -> Lesson:
    """Convert one lesson's page fields to printed footer numbers."""
    ps, pe = page_map.range_to_printed(lesson.page_start, lesson.page_end)
    blocks = [_remap_block(b, page_map) for b in lesson.instructional_blocks]
    tables = [_remap_table(t, page_map) for t in lesson.tables]
    prov = _remap_provenance(lesson.provenance, page_map)
    remapped = lesson.model_copy(
        update={
            "page_start": ps,
            "page_end": pe,
            "instructional_blocks": blocks,
            "tables": tables,
            "provenance": prov,
        }
    )
    # Final safety: every exported *real* page exists in the map values.
    # page==0 unmatched sentinels are intentionally skipped.
    page_map.validate_exported_page(remapped.page_start)
    page_map.validate_exported_page(remapped.page_end)
    for b in remapped.instructional_blocks:
        if b.page != 0:
            page_map.validate_exported_page(b.page)
    return remapped


def _remap_unit(unit: Unit, page_map: PrintedPageMap) -> Unit:
    ov_start = unit.overview_page_start
    ov_end = unit.overview_page_end
    if ov_start is not None and ov_end is not None:
        ov_start, ov_end = page_map.range_to_printed(ov_start, ov_end)
        page_map.validate_exported_page(ov_start)
        page_map.validate_exported_page(ov_end)
    lessons = [remap_lesson(lesson, page_map) for lesson in unit.lessons]
    return unit.model_copy(
        update={
            "overview_page_start": ov_start,
            "overview_page_end": ov_end,
            "lessons": lessons,
        }
    )


def _remap_block(block: InstructionalBlock, page_map: PrintedPageMap) -> InstructionalBlock:
    # page==0 is the unmatched-block sentinel from fill_steps / V13 — keep it.
    # Calling printed_of(0) would raise PageMapError after a GO report was already
    # possible, leaving a trusted-looking report beside an incomplete export.
    if block.page == 0:
        return block
    return block.model_copy(update={"page": page_map.printed_of(block.page)})


def _remap_table(table: Table, page_map: PrintedPageMap) -> Table:
    if table.page == 0:
        return table.model_copy(
            update={"provenance": _remap_provenance(table.provenance, page_map)}
        )
    return table.model_copy(
        update={
            "page": page_map.printed_of(table.page),
            "provenance": _remap_provenance(table.provenance, page_map),
        }
    )


def _remap_provenance(
    prov: Provenance | None, page_map: PrintedPageMap
) -> Provenance | None:
    if prov is None:
        return None
    updates: dict = {}
    # page_start=0 is the "no provenance" sentinel (a Docling table without
    # prov) — 0 is never a valid PDF page, and printed_of(0) would raise
    # PageMapError and kill the whole export over one unattributed table.
    if prov.page_start is not None and prov.page_start > 0:
        # provenance may store a single page or a span
        if prov.page_end is not None and prov.page_end != prov.page_start:
            ps, pe = page_map.range_to_printed(prov.page_start, prov.page_end)
            updates["page_start"] = ps
            updates["page_end"] = pe
        else:
            updates["page_start"] = page_map.printed_of(prov.page_start)
            if prov.page_end is not None:
                updates["page_end"] = page_map.printed_of(prov.page_end)
    return prov.model_copy(update=updates) if updates else prov


def remap_lesson_json_file(
    lesson_path: Path,
    pdf_path: str | Path,
    *,
    page_map: PrintedPageMap | None = None,
) -> Lesson:
    """Load a lesson JSON (PDF indices), remap, and return the printed-page lesson."""
    lesson = Lesson.model_validate_json(Path(lesson_path).read_text(encoding="utf-8"))
    pmap = page_map or build_printed_page_map(pdf_path)
    return remap_lesson(lesson, pmap)
