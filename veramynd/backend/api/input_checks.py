"""Up-front checks on curriculum inputs, so bad files fail with a clear message at upload or
run start instead of deep inside a pipeline stage.

Each check raises ``InputError`` with a sentence a user can act on.
"""

from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

from .layout import PARSER_ROOT


class InputError(ValueError):
    """A curriculum input is unusable; the message says why and what to do."""


def _parse_standards():
    """The parser's own spreadsheet reader, so upload checks match what Parse will do."""
    try:
        from veramynd_parser.standards.spreadsheet import parse_standards  # type: ignore
    except ImportError:
        # In dev, the repo folder "veramynd/veramynd_parser" can shadow the real package as an
        # empty namespace. Put the parser root first and drop that stale import, then retry.
        root = str(PARSER_ROOT)
        if root in sys.path:
            sys.path.remove(root)
        sys.path.insert(0, root)
        for name in [m for m in sys.modules if m == "veramynd_parser" or m.startswith("veramynd_parser.")]:
            del sys.modules[name]
        try:
            from veramynd_parser.standards.spreadsheet import parse_standards  # type: ignore
        except ImportError:
            return None
    return parse_standards


def check_guide_pdf(path: Path, label: str = "The curriculum PDF") -> int:
    """Return the page count; raise InputError if the PDF cannot be parsed."""
    try:
        with path.open("rb") as f:
            head = f.read(1024)
    except OSError as e:
        raise InputError(f"{label} could not be read from disk ({e}).") from e
    if b"%PDF-" not in head:
        raise InputError(
            f"{label} is not a real PDF file (it may be another file type renamed to .pdf). "
            "Export or save the teacher guide as PDF and upload it again."
        )
    try:
        import fitz  # type: ignore  # PyMuPDF, installed with the parser
    except ImportError:
        return 0  # header looked right; deeper checks need PyMuPDF
    try:
        doc = fitz.open(str(path))
    except Exception as e:  # noqa: BLE001 — any open failure means a damaged file
        raise InputError(
            f"{label} is damaged and cannot be opened ({e}). Re-export the PDF and upload it again."
        ) from e
    try:
        if doc.needs_pass:
            raise InputError(
                f"{label} is password-protected. Remove the password (or print to a new PDF) and upload it again."
            )
        pages = doc.page_count
        if pages == 0:
            raise InputError(
                f"{label} has no readable pages (the file looks damaged or incomplete). Re-export it and upload again."
            )
        if not any(doc[i].get_text().strip() for i in range(min(pages, 15))):
            raise InputError(
                f"{label} has no selectable text in its first pages (it looks like a scanned image). "
                "Upload a text-based PDF, or run OCR on it first."
            )
        return pages
    finally:
        doc.close()


def check_standards_xlsx(path: Path, framework: str = "", label: str = "The standards spreadsheet") -> int:
    """Return how many standards the sheet holds; raise InputError if Parse could not use it."""
    try:
        with path.open("rb") as f:
            head = f.read(4)
    except OSError as e:
        raise InputError(f"{label} could not be read from disk ({e}).") from e
    if head[:2] != b"PK":
        if head[:4] == b"\xd0\xcf\x11\xe0":
            raise InputError(
                f"{label} is password-protected or saved in the old .xls format. "
                "Remove the password and save it as .xlsx, then upload it again."
            )
        raise InputError(
            f"{label} is not a real .xlsx file (it may be another file type renamed). "
            "Open it in Excel, save as .xlsx and upload it again."
        )
    parse = _parse_standards()
    if parse is None:
        return 0  # parser not importable here; Parse will validate it
    # Parse a temporary copy: the reader can keep its file open after an error, which would
    # stop a rejected upload's folder from being cleaned up (Windows file locks).
    tmp_dir = Path(tempfile.mkdtemp(prefix="veramynd-check-"))
    copy = tmp_dir / path.name
    try:
        shutil.copyfile(path, copy)
        grade = parse(copy, framework)
    except OSError as e:
        raise InputError(f"{label} could not be read from disk ({e}).") from e
    except Exception as e:  # noqa: BLE001 — the parser's messages describe the problem
        msg = str(e)
        if "required shape" not in msg:
            msg += ". The first sheet needs a header row with the standard code in column 1 and the standard text in column 2"
        raise InputError(f"{label} is not in the expected format: {msg}.") from e
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)
    count = len(getattr(grade, "standards", []) or [])
    if count == 0:
        raise InputError(f"{label} has no standards rows under its header.")
    return count
