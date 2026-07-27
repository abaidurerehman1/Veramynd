"""Printed footer page map — exact PDF→printed mapping (no constant offset)."""

from __future__ import annotations

from pathlib import Path

import pytest

from veramynd_parser.models import InstructionalBlock, Lesson, Provenance
from veramynd_parser.pdf.export_pages import remap_lesson
from veramynd_parser.pdf.page_map import (
    PageMapError,
    PrintedPageMap,
    build_printed_page_map,
)

SAMPLES = Path(__file__).resolve().parents[2] / "data" / "samples"
PDF = SAMPLES / "ELA Grade 1 Module 2 Teacher Guide.pdf"


@pytest.fixture(scope="module")
def page_map() -> PrintedPageMap:
    if not PDF.is_file():
        pytest.skip(f"sample PDF not found: {PDF}")
    return build_printed_page_map(PDF)


def test_map_covers_every_pdf_page(page_map: PrintedPageMap) -> None:
    assert page_map.pdf_page_count == 440
    classified = set(page_map.pdf_to_printed) | set(page_map.unnumbered_pdf_pages)
    assert classified == set(range(1, 441))


def test_no_duplicate_or_decreasing_printed(page_map: PrintedPageMap) -> None:
    vals = list(page_map.pdf_to_printed.values())
    assert len(vals) == len(set(vals))
    ordered = [page_map.pdf_to_printed[p] for p in sorted(page_map.pdf_to_printed)]
    assert ordered == sorted(ordered)


def test_publisher_gaps_not_synthesized(page_map: PrintedPageMap) -> None:
    printed = set(page_map.pdf_to_printed.values())
    for gap in (38, 193, 335):
        assert gap not in printed


def test_lesson1_pdf_12_23_maps_to_printed_39_50(page_map: PrintedPageMap) -> None:
    assert page_map.printed_of(12) == 39
    assert page_map.printed_of(23) == 50
    assert page_map.range_to_printed(12, 23) == (39, 50)


def test_unnumbered_divider_fails_single_lookup(page_map: PrintedPageMap) -> None:
    # Unit divider title cards (no footer) — known PDF pages 1, 166, 308
    for pdf_p in sorted(page_map.unnumbered_pdf_pages):
        with pytest.raises(PageMapError, match="no printed footer"):
            page_map.printed_of(pdf_p)


def test_remap_lesson_exports_printed_only(page_map: PrintedPageMap) -> None:
    lesson = Lesson(
        code="G1M2U1L1",
        grade=1,
        module=2,
        unit=1,
        lesson=1,
        title="Lesson 1",
        page_start=12,
        page_end=23,
        instructional_blocks=[
            InstructionalBlock(
                section="Opening",
                letter="A",
                title="Opening A",
                page=16,
                steps=["…"],
            )
        ],
        provenance=Provenance(source_id="test.pdf", page_start=12, page_end=23),
    )
    out = remap_lesson(lesson, page_map)
    assert out.page_start == 39
    assert out.page_end == 50
    assert out.instructional_blocks[0].page == page_map.printed_of(16)
    assert out.provenance is not None
    assert out.provenance.page_start == 39
    assert out.provenance.page_end == 50


def test_validate_rejects_invented_gap(page_map: PrintedPageMap) -> None:
    with pytest.raises(PageMapError, match="not in the footer map"):
        page_map.validate_exported_page(38)


def test_remap_keeps_unmatched_page_zero_sentinel(page_map: PrintedPageMap) -> None:
    """page==0 means fill_steps never found the block — must not call printed_of(0)."""
    lesson = Lesson(
        code="G1M2U1L1",
        grade=1,
        module=2,
        unit=1,
        lesson=1,
        title="Lesson 1",
        page_start=12,
        page_end=23,
        instructional_blocks=[
            InstructionalBlock(
                section="Opening",
                letter="A",
                title="Opening A",
                page=0,
                steps=[],
            ),
            InstructionalBlock(
                section="Opening",
                letter="B",
                title="Opening B",
                page=16,
                steps=["…"],
            ),
        ],
        provenance=Provenance(source_id="test.pdf", page_start=12, page_end=23),
    )
    out = remap_lesson(lesson, page_map)
    assert out.instructional_blocks[0].page == 0
    assert out.instructional_blocks[1].page == page_map.printed_of(16)
