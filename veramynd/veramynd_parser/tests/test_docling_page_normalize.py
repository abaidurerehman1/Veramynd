"""Unit tests for Docling provenance page normalization (no Docling install)."""

from __future__ import annotations

from types import SimpleNamespace

from veramynd_parser.pdf.docling_parser import (
    _docling_pages_are_zero_based,
    _extract_elements,
    _normalize_docling_page,
)


def test_normalize_docling_pages_shifts_full_zero_based_stream():
    """If any provenance page is 0, every page is treated as 0-based (+1)."""
    assert _normalize_docling_page(0, zero_based=True) == 1
    assert _normalize_docling_page(1, zero_based=True) == 2
    assert _normalize_docling_page(1, zero_based=False) == 1

    class _Prov:
        def __init__(self, page_no: int):
            self.page_no = page_no

    class _Item:
        def __init__(self, page_no: int, text: str):
            self.prov = [_Prov(page_no)]
            self.label = SimpleNamespace(value="text")
            self.text = text

    doc = SimpleNamespace(
        texts=[_Item(0, "a"), _Item(1, "b"), _Item(2, "c")],
        tables=[],
    )
    assert _docling_pages_are_zero_based(doc) is True
    assert [e.page for e in _extract_elements(doc)] == [1, 2, 3]

    doc_one_based = SimpleNamespace(
        texts=[_Item(1, "a"), _Item(2, "b")],
        tables=[],
    )
    assert _docling_pages_are_zero_based(doc_one_based) is False
    assert [e.page for e in _extract_elements(doc_one_based)] == [1, 2]
