"""PDF document adapter.

A thin wrapper over PyMuPDF (fitz) so that the rest of the parser depends on this
small interface, not on the PDF library directly. If the backend ever changes, only
this file does.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import fitz  # PyMuPDF

from ..fonts import Span


@dataclass(frozen=True)
class OutlineEntry:
    """One PDF bookmark: its title and the 1-indexed page it points to."""

    level: int
    title: str
    page: int


@dataclass(frozen=True)
class Line:
    """A reconstructed text line with the classification-relevant span info.

    ``tier`` is filled in by the divider; here we carry the head span so it can be
    classified. ``page`` is 1-indexed.
    """

    page: int
    text: str
    head: Span


class PdfDocument:
    """Read-only view of a PDF, exposing exactly what the parser needs."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self._doc = fitz.open(self.path)

    # -- lifecycle -------------------------------------------------------- #
    def close(self) -> None:
        self._doc.close()

    def __enter__(self) -> "PdfDocument":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # -- basic properties ------------------------------------------------- #
    @property
    def page_count(self) -> int:
        return self._doc.page_count

    @property
    def source_id(self) -> str:
        return self.path.name

    # -- structure -------------------------------------------------------- #
    def outline(self) -> list[OutlineEntry]:
        """The PDF's bookmarks, in document order. Empty if the PDF has none."""
        return [
            OutlineEntry(level=lvl, title=title, page=page)
            for lvl, title, page in self._doc.get_toc()
        ]

    # -- text ------------------------------------------------------------- #
    def _require_page(self, page: int) -> None:
        if page < 1 or page > self.page_count:
            raise ValueError(
                f"{self.source_id}: page {page} out of range "
                f"(valid pages are 1..{self.page_count})"
            )

    def _require_range(self, page_start: int, page_end: int) -> None:
        if page_end < page_start:
            raise ValueError(
                f"{self.source_id}: inverted page range {page_start}-{page_end}"
            )
        self._require_page(page_start)
        self._require_page(page_end)

    def page_text(self, page: int) -> str:
        """Raw text of a 1-indexed page."""
        self._require_page(page)
        return self._doc[page - 1].get_text("text")

    def text_range(self, page_start: int, page_end: int) -> str:
        """Concatenated raw text across an inclusive 1-indexed page range."""
        self._require_range(page_start, page_end)
        return "\n".join(
            self._doc[p - 1].get_text("text")
            for p in range(page_start, page_end + 1)
        )

    def lines(self, page_start: int, page_end: int) -> list[Line]:
        """Reconstructed lines across a page range, each with its head span.

        Only the first span of each line is retained (the head), which is what the
        tier classifier keys on — headings are homogeneous, so the head is
        representative.
        """
        self._require_range(page_start, page_end)
        out: list[Line] = []
        for page in range(page_start, page_end + 1):
            data = self._doc[page - 1].get_text("dict")
            for block in data["blocks"]:
                for line in block.get("lines", []):
                    spans = line["spans"]
                    if not spans:
                        continue
                    text = "".join(s["text"] for s in spans)
                    if not text.strip():
                        continue
                    head = spans[0]
                    out.append(
                        Line(
                            page=page,
                            text=text,
                            head=Span(
                                text=head["text"],
                                font=head["font"],
                                size=head["size"],
                                flags=head.get("flags", 0),
                            ),
                        )
                    )
        return out
