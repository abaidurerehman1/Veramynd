"""Standards spreadsheet parser — flat rows to a grade-indexed tree.

The Georgia ELA standards arrive as a flat spreadsheet: ``Code | Standard Text |
Notes``. The hierarchy is a tree, but it is encoded in the *code string*, not in the
sheet's columns:

    1.F           domain
    1.F.PA        big idea
    1.F.PA.4      standard
    1.F.PA.4.d    substandard

The level is derived from the code's dot-depth. The 'Notes' column nominally records
the level but is empty on the large majority of rows, so trusting it would mislabel
almost everything — we ignore it for level and read depth instead. The parent of any
node is its code with the last segment removed.
"""

from __future__ import annotations

from pathlib import Path

import openpyxl

from ..models import GradeStandards, Provenance, Standard, StandardLevel

_LEVEL_BY_DEPTH = {
    1: StandardLevel.DOMAIN,
    2: StandardLevel.BIG_IDEA,
    3: StandardLevel.STANDARD,
}

_REQUIRED_HEADERS = ("code", "standard text")


class SpreadsheetStructureError(ValueError):
    """Raised when the standards workbook shape is invalid."""


class MultiGradeSheetError(SpreadsheetStructureError):
    """Raised when a single sheet contains more than one grade prefix."""


class UngradedCodeError(ValueError):
    """A standard code's leading segment isn't a single grade integer."""


def level_of(code: str) -> StandardLevel:
    """Derive the hierarchy level from the code's dot-depth (not the Notes column)."""
    return _LEVEL_BY_DEPTH.get(code.count("."), StandardLevel.SUBSTANDARD)


def parent_of(code: str) -> str | None:
    """The parent code: this code with its last dotted segment removed."""
    return code.rsplit(".", 1)[0] if code.count(".") >= 2 else None


def grade_of(code: str) -> int:
    """Grade prefix of a code, e.g. ``1.F.PA.4`` → 1, ``K.F.PA.1`` → 0 (K)."""
    head = code.split(".", 1)[0]
    if head.isdigit():
        return int(head)
    if head.upper() == "K":
        return 0
    raise UngradedCodeError(
        f"standard code {code!r}: leading segment {head!r} is not a single grade "
        f"integer or K (a banded code like '6-8.RL.1' needs to be expanded to one row "
        f"per grade before parsing, not silently left ungraded)"
    )


def _split_label(text: str) -> tuple[str, str]:
    """Split a 'Prefix: description' standard text into (label, text)."""
    if ":" in text:
        head, _, tail = text.partition(":")
        if len(head) <= 40 and "." not in head:
            return head.strip(), tail.strip()
    return "", text.strip()


def _normalize_header(value: object) -> str:
    return " ".join(str(value or "").strip().lower().split())


def _validate_header(row: tuple[object, ...] | None, *, sheet: str) -> None:
    if not row or all(c is None or str(c).strip() == "" for c in row):
        raise SpreadsheetStructureError(
            f"{sheet}: missing header row — expected columns like "
            f"'Code | Standard Text | Notes'"
        )
    headers = [_normalize_header(c) for c in row]
    if not headers[0] or "code" not in headers[0]:
        raise SpreadsheetStructureError(
            f"{sheet}: first column header must identify the code "
            f"(got {row[0]!r}); required shape: Code | Standard Text | …"
        )
    if len(headers) < 2 or not headers[1]:
        raise SpreadsheetStructureError(
            f"{sheet}: second column header (standard text) is missing or empty"
        )
    # Soft check: warn via error if clearly wrong second header.
    if headers[1] not in {"standard text", "text", "description", "standard"} and (
        "standard" not in headers[1] and "text" not in headers[1]
    ):
        raise SpreadsheetStructureError(
            f"{sheet}: second column header should be standard text "
            f"(got {row[1]!r})"
        )


def parse_standards(
    path: str | Path,
    framework: str = "GA ELA",
    sheet: str | None = None,
) -> GradeStandards:
    """Parse a standards spreadsheet into a ``GradeStandards`` tree.

    Expects a header row with a code column first and standard text second. Validates
    structure up front. Raises if the sheet mixes multiple grade prefixes.
    """
    path = Path(path)
    try:
        wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
    except Exception as e:
        raise SpreadsheetStructureError(f"cannot open workbook {path.name}: {e}") from e

    try:
        ws = wb[sheet] if sheet else wb.worksheets[0]
        rows_iter = ws.iter_rows(values_only=True)
        try:
            header = next(rows_iter)
        except StopIteration:
            raise SpreadsheetStructureError(f"{ws.title}: workbook sheet is empty") from None
        _validate_header(header, sheet=ws.title)

        standards: list[Standard] = []
        grades_seen: set[int] = set()
        empty_text_rows: list[int] = []
        seen_codes: dict[str, int] = {}

        for row_idx, row in enumerate(rows_iter, start=2):
            if not row or row[0] is None:
                continue
            code = str(row[0]).strip()
            if not code:
                continue
            # data_only=True leaves uncached formula cells as None — treat as error
            # when the cell looks like a formula string was expected.
            raw_text = row[1] if len(row) > 1 else None
            if isinstance(raw_text, str) and raw_text.startswith("="):
                raise SpreadsheetStructureError(
                    f"{ws.title} row {row_idx}: standard text is an unevaluated "
                    f"formula ({raw_text!r}). Open/save the workbook in Excel so "
                    f"cached values exist, or replace formulas with plain text."
                )
            text = str(raw_text).strip() if raw_text is not None else ""
            if not text:
                empty_text_rows.append(row_idx)
                continue
            prev = seen_codes.get(code)
            if prev is not None:
                raise SpreadsheetStructureError(
                    f"{ws.title} row {row_idx}: duplicate standard code {code!r} "
                    f"(also at row {prev})"
                )
            seen_codes[code] = row_idx
            label, body = _split_label(text)
            g = grade_of(code)
            grades_seen.add(g)
            standards.append(
                Standard(
                    code=code,
                    level=level_of(code),
                    label=label,
                    text=body,
                    parent_code=parent_of(code),
                    grade=g,
                    provenance=Provenance(source_id=path.name, sheet=ws.title, row=row_idx),
                )
            )
    finally:
        wb.close()

    if not standards:
        detail = (
            f" ({len(empty_text_rows)} row(s) had a code but empty standard text)"
            if empty_text_rows
            else ""
        )
        raise SpreadsheetStructureError(
            f"{path.name}: no standards rows found after the header{detail}"
        )

    if len(grades_seen) > 1:
        raise MultiGradeSheetError(
            f"{path.name}: sheet mixes multiple grades {sorted(grades_seen)} — "
            f"split into one sheet per grade (each Standard still carries its own "
            f"grade; GradeStandards.grade cannot be a single value for this file)"
        )
    if not grades_seen:
        raise SpreadsheetStructureError(
            f"{path.name}: no grade prefixes could be derived from standard codes"
        )

    if empty_text_rows:
        preview = empty_text_rows[:5]
        more = "" if len(empty_text_rows) <= 5 else f" (+{len(empty_text_rows) - 5} more)"
        raise SpreadsheetStructureError(
            f"{path.name}: {len(empty_text_rows)} row(s) have a code but empty "
            f"standard text (rows {preview}{more}) — fix or remove them before parsing"
        )

    grade = next(iter(grades_seen))
    return GradeStandards(grade=grade, framework=framework, standards=standards)
