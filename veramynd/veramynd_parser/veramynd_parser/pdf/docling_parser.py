"""Docling adapter — the primary content parser.

Docling performs layout analysis and table-structure recovery. Parses are
content-addressed cached. ``docling`` is imported lazily so the lightweight
PyMuPDF path never requires it.
"""

from __future__ import annotations

import hashlib
import os
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from ..config import Config
from ..paths import resolve_package_relative


@dataclass(frozen=True)
class Element:
    """One labeled text element in reading order."""

    label: str
    text: str
    page: int


@dataclass(frozen=True)
class DoclingTable:
    """A structured table with row-major cells."""

    page: int
    cells: list[list[str]]

    @property
    def n_rows(self) -> int:
        return len(self.cells)

    @property
    def n_cols(self) -> int:
        return len(self.cells[0]) if self.cells else 0


def _docling_version() -> str:
    import importlib.metadata as md

    return md.version("docling")


def _content_digest(path: Path, cache_dir: Path) -> str:
    """SHA256 prefix of PDF bytes.

    Always hashes file contents. A size+mtime sidecar only *stores* the digest
    for diagnostics; it is never trusted as a substitute for rehashing (same
    size/mtime after a content rewrite would otherwise serve a stale parse).
    """
    digest = hashlib.sha256(path.read_bytes()).hexdigest()[:16]
    try:
        st = path.stat()
        meta_name = f".digest.{path.name}.{st.st_size}.{st.st_mtime_ns}"
        meta_path = cache_dir / meta_name
        meta_path.write_text(digest, encoding="utf-8")
    except OSError:
        pass
    return digest


def _cache_key(path: Path, ocr: bool, cfg: Config, cache_dir: Path) -> str:
    # Exact Docling version string (no dot-stripping) avoids 2.10 vs 2.1.0 collisions.
    version = _docling_version()
    digest = _content_digest(path, cache_dir)
    version_tag = hashlib.sha256(version.encode("utf-8")).hexdigest()[:12]
    return (
        f"{digest}-docling-{version}-v{version_tag}"
        f"-ocr{int(ocr)}-tables{int(cfg.docling_tables)}"
    )


def _has_text_layer(path: Path, cfg: Config, sample: int = 24, min_chars: int = 50) -> bool:
    """True if the PDF already carries an extractable text layer on most pages."""
    import fitz

    doc = fitz.open(path)
    try:
        n = doc.page_count
        if n == 0:
            return False
        step = max(1, n // sample)
        checked = with_text = 0
        for i in range(0, n, step):
            checked += 1
            if len(doc[i].get_text("text").strip()) >= min_chars:
                with_text += 1
    finally:
        doc.close()
    return checked > 0 and (with_text / checked) >= cfg.ocr_text_coverage_threshold


def resolve_ocr(path: Path, cfg: Config) -> bool:
    """Decide whether OCR runs for this document, per the configured mode."""
    if cfg.ocr_mode == "on":
        return True
    if cfg.ocr_mode == "off":
        return False
    return not _has_text_layer(path, cfg)


class DoclingParse:
    """Parsed Docling view of a document: labeled elements and tables, with a cache."""

    def __init__(self, source_id: str, elements: list[Element], tables: list[DoclingTable]):
        self.source_id = source_id
        self.elements = elements
        self.tables = tables

    ocr_used: bool = False

    @classmethod
    def parse(cls, path: str | Path, cfg: Config | None = None) -> "DoclingParse":
        """Parse (or load from cache) a document with Docling."""
        cfg = cfg or Config()
        path = Path(path)
        ocr = resolve_ocr(path, cfg)
        doc = _load_or_convert(path, cfg, ocr)
        parsed = cls(path.name, _extract_elements(doc), _extract_tables(doc))
        parsed.ocr_used = ocr
        return parsed

    def elements_in_range(self, page_start: int, page_end: int) -> list[Element]:
        return [e for e in self.elements if page_start <= e.page <= page_end]

    def tables_in_range(self, page_start: int, page_end: int) -> list[DoclingTable]:
        return [t for t in self.tables if page_start <= t.page <= page_end]


def resolve_docling_cache_dir(cfg: Config) -> Path:
    """Relative ``cfg.docling_cache_dir`` resolves against the package root."""
    return resolve_package_relative(cfg.docling_cache_dir)


@contextmanager
def _file_lock(lock_path: Path, *, timeout_s: float = 600.0, poll_s: float = 0.1):
    """Exclusive lock via O_EXCL lockfile (P3). Works on Windows and POSIX."""
    deadline = time.monotonic() + timeout_s
    while True:
        try:
            fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            try:
                os.write(fd, str(os.getpid()).encode("ascii", errors="ignore"))
                yield
            finally:
                os.close(fd)
                try:
                    lock_path.unlink()
                except OSError:
                    pass
            return
        except FileExistsError:
            if time.monotonic() >= deadline:
                raise TimeoutError(f"timed out waiting for cache lock: {lock_path}")
            time.sleep(poll_s)


def _load_or_convert(path: Path, cfg: Config, ocr: bool):
    """Return a DoclingDocument, from cache if present, else convert and cache it."""
    from docling_core.types.doc import DoclingDocument

    cache_dir = resolve_docling_cache_dir(cfg)
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_file = cache_dir / f"{_cache_key(path, ocr, cfg, cache_dir)}.docling.json"
    lock_path = cache_file.with_suffix(cache_file.suffix + ".lock")

    if cache_file.exists():
        return DoclingDocument.load_from_json(cache_file)

    with _file_lock(lock_path):
        # Another writer may have finished while we waited.
        if cache_file.exists():
            return DoclingDocument.load_from_json(cache_file)

        doc = _convert(path, cfg, ocr)
        tmp_file = cache_file.with_suffix(f".{os.getpid()}.tmp")
        try:
            doc.save_as_json(tmp_file)
            tmp_file.replace(cache_file)
            tmp_file = None  # type: ignore[assignment]
        finally:
            if tmp_file is not None and Path(tmp_file).exists():
                try:
                    Path(tmp_file).unlink()
                except OSError:
                    pass
        return doc


def _convert(path: Path, cfg: Config, ocr: bool):
    """Run Docling's conversion pipeline (the slow path)."""
    from docling.datamodel.base_models import InputFormat
    from docling.datamodel.pipeline_options import PdfPipelineOptions
    from docling.document_converter import DocumentConverter, PdfFormatOption

    opts = PdfPipelineOptions()
    opts.do_ocr = ocr
    opts.do_table_structure = cfg.docling_tables
    converter = DocumentConverter(
        format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=opts)}
    )
    return converter.convert(str(path)).document


def _extract_elements(doc) -> list[Element]:
    """Flatten a DoclingDocument's text items into labeled, page-tagged elements."""
    out: list[Element] = []
    for item in doc.texts:
        if not item.prov:
            continue
        label = item.label.value if hasattr(item.label, "value") else str(item.label)
        out.append(Element(label=label, text=item.text or "", page=item.prov[0].page_no))
    return out


def _extract_tables(doc) -> list[DoclingTable]:
    """Extract structured tables, row-major, with page provenance."""
    out: list[DoclingTable] = []
    for tb in doc.tables:
        page = tb.prov[0].page_no if tb.prov else 0
        cells: list[list[str]] = []
        try:
            df = tb.export_to_dataframe(doc)
            cells = [[str(c) for c in df.columns]]
            cells += [[("" if v is None else str(v)) for v in row] for row in df.values.tolist()]
        except (AttributeError, TypeError, ValueError, KeyError):
            try:
                grid = tb.data.grid
                cells = [[(cell.text or "") for cell in row] for row in grid]
            except (AttributeError, TypeError, ValueError):
                cells = []
        out.append(DoclingTable(page=page, cells=cells))
    return out
