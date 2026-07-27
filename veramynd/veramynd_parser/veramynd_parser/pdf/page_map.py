"""Printed footer page map — PDF index → publisher page number.

Docling / PyMuPDF / bookmarks use 1-based PDF page indices. The EL Education
teacher guide prints a different page number in the footer (e.g. PDF 12 → 39).

This module builds an **exact** per-page map by reading each page's footer.
It never applies a constant offset and never synthesizes missing publisher
numbers (e.g. 38, 193, 335).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import fitz

_CURRICULUM_PAGE = re.compile(r"Curriculum\s+(\d{1,4})\s*$", re.I)
_BARE_PAGE = re.compile(r"^\d{1,4}$")
# Unit divider title cards have no footer number — only this short cover text.
_DIVIDER_HINT = re.compile(
    r"Grade\s*\d+\s*:\s*Module\s*\d+.*Unit\s*\d+\s*:.*Overview\s+and\s+Lessons",
    re.I | re.S,
)


class PageMapError(RuntimeError):
    """Raised when the printed-page map cannot be built or applied safely."""


@dataclass(frozen=True)
class PrintedPageMap:
    """Exact mapping from PDF page index (1-based) to printed footer page."""

    source_id: str
    pdf_page_count: int
    pdf_to_printed: dict[int, int]
    unnumbered_pdf_pages: frozenset[int] = field(default_factory=frozenset)

    def printed_of(self, pdf_page: int) -> int:
        """Convert one PDF page index to its printed footer number."""
        if pdf_page in self.pdf_to_printed:
            return self.pdf_to_printed[pdf_page]
        if pdf_page in self.unnumbered_pdf_pages:
            raise PageMapError(
                f"PDF page {pdf_page} has no printed footer number "
                f"(unit divider / title card in {self.source_id}). "
                f"Cannot export it as a page reference."
            )
        raise PageMapError(
            f"PDF page {pdf_page} is outside the map for {self.source_id} "
            f"(valid PDF pages: 1..{self.pdf_page_count})."
        )

    def range_to_printed(self, pdf_start: int, pdf_end: int) -> tuple[int, int]:
        """Map an inclusive PDF range to printed start/end.

        Uses the first and last *mapped* pages in the range. Unnumbered divider
        pages inside the range are skipped (never invent footer numbers).
        """
        if pdf_start > pdf_end:
            raise PageMapError(f"Invalid PDF range {pdf_start}-{pdf_end}")
        mapped = [
            self.pdf_to_printed[p]
            for p in range(pdf_start, pdf_end + 1)
            if p in self.pdf_to_printed
        ]
        if not mapped:
            raise PageMapError(
                f"No printed footer numbers found in PDF range "
                f"{pdf_start}-{pdf_end} of {self.source_id}"
            )
        return mapped[0], mapped[-1]

    def validate_exported_page(self, printed: int) -> None:
        if printed not in self.pdf_to_printed.values():
            raise PageMapError(
                f"Exported printed page {printed} is not in the footer map "
                f"for {self.source_id} (refusing to invent publisher gaps)."
            )


def extract_footer_page_number(page: fitz.Page) -> int | None:
    """Read the printed page number from a single PDF page, or None if absent."""
    text = page.get_text("text") or ""
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    if not lines:
        return None

    # Fast path: unit divider title cards — intentionally unnumbered.
    joined = "\n".join(lines)
    if len(lines) <= 6 and _DIVIDER_HINT.search(joined.replace("\n", " ")):
        return None

    edge = lines[:6] + lines[-6:]
    for ln in edge:
        m = _CURRICULUM_PAGE.search(ln)
        if m:
            return int(m.group(1))

    # Running-header bare number next to module title (common on verso pages).
    for i, ln in enumerate(lines[:8]):
        if not _BARE_PAGE.match(ln):
            continue
        nearby = " ".join(lines[max(0, i - 2) : i + 3]).lower()
        if any(
            key in nearby
            for key in (
                "sun, moon",
                "unit ",
                "grade ",
                "curriculum",
                "module ",
            )
        ):
            return int(ln)

    return None


def build_printed_page_map(pdf_path: str | Path) -> PrintedPageMap:
    """Scan every page and build pdf_page → printed_page (exact footer read)."""
    path = Path(pdf_path)
    doc = fitz.open(path)
    try:
        pdf_to_printed: dict[int, int] = {}
        unnumbered: set[int] = set()

        for pdf_page in range(1, doc.page_count + 1):
            printed = extract_footer_page_number(doc.load_page(pdf_page - 1))
            if printed is None:
                unnumbered.add(pdf_page)
            else:
                pdf_to_printed[pdf_page] = printed

        _validate_map(path.name, doc.page_count, pdf_to_printed, unnumbered)

        return PrintedPageMap(
            source_id=path.name,
            pdf_page_count=doc.page_count,
            pdf_to_printed=pdf_to_printed,
            unnumbered_pdf_pages=frozenset(unnumbered),
        )
    finally:
        doc.close()


def _validate_map(
    source_id: str,
    page_count: int,
    pdf_to_printed: dict[int, int],
    unnumbered: set[int],
) -> None:
    # Every PDF page must be classified.
    classified = set(pdf_to_printed) | unnumbered
    missing = [p for p in range(1, page_count + 1) if p not in classified]
    if missing:
        raise PageMapError(
            f"{source_id}: PDF pages not classified as numbered or unnumbered: {missing}"
        )

    if len(pdf_to_printed) + len(unnumbered) != page_count:
        raise PageMapError(f"{source_id}: internal page-map coverage mismatch")

    # No duplicate printed numbers.
    printed_vals = list(pdf_to_printed.values())
    if len(printed_vals) != len(set(printed_vals)):
        seen: dict[int, int] = {}
        dups: list[str] = []
        for pdf_p, pr in sorted(pdf_to_printed.items()):
            if pr in seen:
                dups.append(f"printed {pr} on PDF {seen[pr]} and PDF {pdf_p}")
            else:
                seen[pr] = pdf_p
        raise PageMapError(
            f"{source_id}: duplicate printed page numbers: " + "; ".join(dups)
        )

    # Printed numbers must never decrease along PDF order.
    prev_pdf = None
    prev_pr = None
    for pdf_p in sorted(pdf_to_printed):
        pr = pdf_to_printed[pdf_p]
        if prev_pr is not None and pr < prev_pr:
            raise PageMapError(
                f"{source_id}: printed pages decrease between PDF {prev_pdf} "
                f"(printed {prev_pr}) and PDF {pdf_p} (printed {pr})"
            )
        prev_pdf, prev_pr = pdf_p, pr

    # Unnumbered pages must look like divider cards (already filtered in extract);
    # require they are sparse — fail if too many (likely extractor regression).
    if len(unnumbered) > max(3, page_count // 50):
        raise PageMapError(
            f"{source_id}: too many unnumbered pages ({sorted(unnumbered)[:20]}…) — "
            f"footer extraction likely failed"
        )
