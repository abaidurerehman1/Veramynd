"""Build client correlation DOCX/XLSX from judge (or master) alignment rows.

Matches ``Example Output Format GA_ELA_G1.docx`` Table-1 style and the skill-
named parent roll-up wording in ``Rollup_Format_Example_for_Engineer.xlsx``.

Publisher-agnostic: same pipeline for any curriculum — pass judge/CSV rows +
standards tree + program/guide labels. Framework-specific display names are
parameters, not hard-coded publisher branches.
"""

from __future__ import annotations

import csv
import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.oxml import OxmlElement
from docx.shared import Pt, Inches
from openpyxl import Workbook, load_workbook

from ..text_utils import atomic_write_text

CLIENT_FORMAT_VERSION = "1.2-client-rollup"
_FONT = "Times New Roman"
_SIZE = Pt(10)  # 20 half-points, matches the example
_GRAY = "D9D9D9"

DOMAIN_DISPLAY = {
    "1.F": "FOUNDATIONS",
    "1.P": "PRACTICES",
    "1.L": "LANGUAGE",
    "1.T": "TEXTS",
}

_DOMAIN_SECTION = {
    "1.F": "Foundations",
    "1.P": "Practices",
    "1.L": "Language",
    "1.T": "Texts",
}

# Roman numerals for big-idea ordering within a domain (presentation only).
_ROMAN = (
    "I",
    "II",
    "III",
    "IV",
    "V",
    "VI",
    "VII",
    "VIII",
    "IX",
    "X",
    "XI",
    "XII",
    "XIII",
    "XIV",
    "XV",
)

_IC_TAG_RE = re.compile(r"\s*\(([IC]|I/C)\)\s*$", re.IGNORECASE)
_WS_RE = re.compile(r"\s+")


class ClientFormatError(ValueError):
    pass


def _set_cell_shading(cell: Any, hex_color: str) -> None:
    tc = cell._tc
    tcPr = tc.get_or_add_tcPr()
    for old in tcPr.findall(qn("w:shd")):
        tcPr.remove(old)
    shd = OxmlElement("w:shd")
    shd.set(qn("w:fill"), hex_color)
    shd.set(qn("w:val"), "clear")
    tcPr.append(shd)


def _clear_cell(cell: Any) -> None:
    cell.text = ""


def _style_run(run: Any, *, bold: bool = False) -> None:
    run.bold = bold
    run.font.name = _FONT
    run.font.size = _SIZE
    rPr = run._element.get_or_add_rPr()
    rFonts = rPr.find(qn("w:rFonts"))
    if rFonts is None:
        rFonts = OxmlElement("w:rFonts")
        rPr.append(rFonts)
    rFonts.set(qn("w:ascii"), _FONT)
    rFonts.set(qn("w:hAnsi"), _FONT)
    rFonts.set(qn("w:cs"), _FONT)
    rFonts.set(qn("w:eastAsia"), _FONT)


def _set_cell_text(
    cell: Any,
    text: str,
    *,
    bold: bool = False,
    center: bool = False,
) -> None:
    _clear_cell(cell)
    p = cell.paragraphs[0]
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER if center else WD_ALIGN_PARAGRAPH.LEFT
    p.paragraph_format.space_before = Pt(1)
    p.paragraph_format.space_after = Pt(1)
    run = p.add_run(text)
    _style_run(run, bold=bold)


def _set_multiline_cell(
    cell: Any,
    lines: list[str],
    *,
    bold_line_prefixes: list[str] | None = None,
) -> None:
    """Write lines into a cell; optionally bold a matching prefix on each line."""
    _clear_cell(cell)
    if not lines:
        return
    prefixes = bold_line_prefixes or []
    p = cell.paragraphs[0]
    p.paragraph_format.space_before = Pt(1)
    p.paragraph_format.space_after = Pt(1)
    for i, line in enumerate(lines):
        if i:
            p.add_run().add_break()
        prefix = prefixes[i] if i < len(prefixes) else None
        if prefix and line.startswith(prefix):
            r1 = p.add_run(prefix)
            _style_run(r1, bold=True)
            rest = line[len(prefix) :]
            if rest:
                r2 = p.add_run(rest)
                _style_run(r2, bold=False)
        else:
            r = p.add_run(line)
            _style_run(r, bold=False)


_PARTIAL_NOTE = "This standard is partially met."
_FULL_NOTE = "This standard is fully met."


def _beyond_scope_note(guide_label: str = "this program module") -> str:
    label = (guide_label or "").strip() or "this program module"
    return f"This standard is beyond the scope of {label}."


def _short_partial_explanation(rationales: list[str], *, max_len: int = 280) -> str:
    """Pick a concise client-facing explanation from a partial rationale."""
    for raw in rationales:
        text = " ".join(str(raw).split())
        if not text:
            continue
        text = text.replace("⚑ REVIEW:", "").strip()
        parts = [p.strip() for p in text.replace("? ", ". ").split(". ") if p.strip()]
        chosen: list[str] = []
        for p in parts:
            low = p.lower()
            if any(
                k in low
                for k in (
                    "partial",
                    "not met",
                    "however",
                    "missing",
                    "only",
                    "does not",
                    "never",
                    "but ",
                )
            ):
                chosen.append(p if p.endswith(".") else p + ".")
            if len(" ".join(chosen)) >= 120:
                break
        expl = " ".join(chosen) if chosen else (
            parts[0] + ("." if parts and not parts[0].endswith(".") else "")
        )
        if len(expl) > max_len:
            expl = expl[: max_len - 1].rsplit(" ", 1)[0] + "…"
        return expl
    return ""


def skill_phrase(standard_text: str) -> str:
    """Plain-language skill name from a leaf standard text (no letter codes)."""
    t = _IC_TAG_RE.sub("", (standard_text or "").strip())
    t = _WS_RE.sub(" ", t).strip().rstrip(".")
    if not t:
        return ""
    if len(t) > 160 and ";" in t:
        t = t.split(";", 1)[0].strip().rstrip(".")
    if t and t[0].isupper():
        t = t[0].lower() + t[1:]
    return t


def _join_skills(skills: list[str], *, conj: str = "and") -> str:
    items = [s.strip() for s in skills if s and s.strip()]
    if not items:
        return ""
    if len(items) == 1:
        return items[0]
    if len(items) == 2:
        return f"{items[0]} {conj} {items[1]}"
    return ", ".join(items[:-1]) + f", {conj} {items[-1]}"


def domain_section_for_code(code: str) -> str:
    parts = (code or "").split(".")
    if len(parts) >= 2:
        key = f"{parts[0]}.{parts[1]}"
        if key in _DOMAIN_SECTION:
            return _DOMAIN_SECTION[key]
        return key
    return (code or "").split(".", 1)[0] or "Standards"


def build_parent_rollups(
    standards: list[dict[str, Any]],
    teacher_by_code: dict[str, dict[str, Any]],
    *,
    guide_label: str = "Module 2",
) -> dict[str, dict[str, Any]]:
    """Parent code → {alignment, statement, section, parent_label, …}.

    Matches ``Example Output Format`` + ``Rollup_Format_Example_for_Engineer``:
    parent materials cells always open with the parent skill title, then either
    skill-named partial/full prose or a beyond-scope note for the guide.
    """
    children_by_parent: dict[str, list[dict[str, Any]]] = defaultdict(list)
    parents: dict[str, dict[str, Any]] = {}
    for std in standards:
        level = std.get("level")
        code = str(std.get("code") or "").strip()
        if not code:
            continue
        if level == "standard":
            parents[code] = std
        elif level == "substandard":
            parent = str(std.get("parent_code") or "").strip()
            if parent:
                children_by_parent[parent].append(std)

    out: dict[str, dict[str, Any]] = {}
    for parent_code, kids in children_by_parent.items():
        parent = parents.get(parent_code) or {"code": parent_code}
        supported: list[str] = []
        partial_only: list[str] = []
        missing: list[str] = []
        for kid in kids:
            code = str(kid.get("code") or "").strip()
            skill = skill_phrase(str(kid.get("text") or ""))
            if not skill:
                skill = code
            agg = teacher_by_code.get(code)
            if not agg or not agg.get("pages"):
                missing.append(skill)
            elif int(agg.get("full_n") or 0) > 0:
                supported.append(skill)
            else:
                partial_only.append(skill)

        section = domain_section_for_code(parent_code)
        parent_label = _parent_label(parent)
        base = {
            "section": section,
            "parent_code": parent_code,
            "parent_label": parent_label,
            "supported_skills": supported,
            "partial_skills": partial_only,
            "missing_skills": missing,
        }

        if not supported and not partial_only:
            beyond = _beyond_scope_note(guide_label)
            if missing:
                # Match fixed client DOCX: "None of the cited lessons ask students to …"
                ask = _join_skills(missing, conj="or").replace(", and ", ", or ")
                beyond += (
                    " None of the cited lessons ask students to "
                    f"{ask}."
                )
            out[parent_code] = {
                **base,
                "alignment": "beyond_scope",
                "statement": beyond,
            }
            continue

        if not missing and not partial_only:
            covered = supported + partial_only
            full_stmt = _FULL_NOTE
            if covered:
                full_stmt += (
                    " Citations show students "
                    f"{_join_skills(covered)}."
                )
            out[parent_code] = {
                **base,
                "alignment": "fully_met",
                "statement": full_stmt,
            }
            continue

        covered = supported + partial_only
        stmt = (
            f"{_PARTIAL_NOTE} Citations show students {_join_skills(covered)}."
            if covered
            else _PARTIAL_NOTE
        )
        if missing:
            stmt += (
                " However, none of the cited lessons ask students to "
                f"{_join_skills(missing, conj='or')}."
            )
        if partial_only:
            stmt += (
                " Where a covered skill appears only in part, student performance "
                "is incomplete relative to the full skill named by the standard."
            )
        out[parent_code] = {
            **base,
            "alignment": "partially_met",
            "statement": stmt,
        }
    return out


def _fill_leaf_material_cells(
    tg_cell: Any,
    other_cell: Any,
    agg: dict[str, Any] | None,
    *,
    guide_label: str,
) -> None:
    """Apply client notes: beyond-scope / partial-met (+ explanation when possible)."""
    pages = _teacher_pages_text(agg)
    prefix = f"{guide_label}:"
    if not pages:
        note = _beyond_scope_note(guide_label)
        _set_cell_text(tg_cell, note, bold=False)
        _set_cell_text(other_cell, note, bold=False)
        return

    only_partial = (
        bool(agg)
        and int(agg.get("partial_n") or 0) > 0
        and int(agg.get("full_n") or 0) == 0
    )
    if only_partial:
        expl = _short_partial_explanation(list(agg.get("partial_rationales") or []))
        note_line = _PARTIAL_NOTE
        if expl:
            note_line = f"{_PARTIAL_NOTE} {expl}"
        lines = [note_line, f"{prefix} {pages}"]
        _set_multiline_cell(
            tg_cell,
            lines,
            bold_line_prefixes=["", prefix],
        )
    else:
        _set_multiline_cell(
            tg_cell,
            [f"{prefix} {pages}"],
            bold_line_prefixes=[prefix],
        )
    other = _other_materials_cell(agg)
    _set_cell_text(other_cell, other, bold=False)


def _add_bottom_border(paragraph: Any) -> None:
    pPr = paragraph._p.get_or_add_pPr()
    pBdr = OxmlElement("w:pBdr")
    bottom = OxmlElement("w:bottom")
    bottom.set(qn("w:val"), "single")
    bottom.set(qn("w:sz"), "4")
    bottom.set(qn("w:space"), "1")
    bottom.set(qn("w:color"), "000000")
    pBdr.append(bottom)
    pPr.append(pBdr)


def _configure_continuing_page_header(
    doc: Document,
    *,
    program_name: str,
    framework_header: str,
) -> None:
    """Header on every page except the first (matches the example DOCX)."""
    section = doc.sections[0]
    section.different_first_page_header_footer = True
    fp = section.first_page_header
    for p in list(fp.paragraphs):
        p.text = ""

    header = section.header
    for p in list(header.paragraphs):
        p.clear()
    while len(header.paragraphs) > 1:
        p = header.paragraphs[-1]._element
        p.getparent().remove(p)

    line1 = header.paragraphs[0]
    line1.alignment = WD_ALIGN_PARAGRAPH.LEFT
    r1 = line1.add_run(f"{program_name}, Grade 1 correlated to the")
    _style_run(r1, bold=True)

    line2 = header.add_paragraph()
    line2.alignment = WD_ALIGN_PARAGRAPH.LEFT
    r2 = line2.add_run(framework_header)
    _style_run(r2, bold=True)
    _add_bottom_border(line2)


def _add_title_page(
    doc: Document,
    *,
    program_name: str,
    grade_label: str,
    framework_title_lines: list[str],
) -> None:
    """Centered first-page title block from the example."""

    def _title_line(text: str) -> None:
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = p.add_run(text)
        _style_run(run, bold=True)

    _title_line(f"{program_name}, {grade_label}")
    doc.add_paragraph()
    _title_line("correlated to")
    doc.add_paragraph()
    for line in framework_title_lines:
        _title_line(line)
    doc.add_paragraph()
    _title_line(grade_label)
    doc.add_paragraph()


def format_page_list(pages: Iterable[int | float | str | None]) -> str:
    """Compress page numbers like the example: ``pp. 74, 84, 91–92``."""
    clean: list[int] = []
    for raw in pages:
        if raw is None or raw == "":
            continue
        try:
            clean.append(int(float(raw)))
        except (TypeError, ValueError):
            continue
    clean = sorted(set(p for p in clean if p > 0))
    if not clean:
        return ""

    ranges: list[tuple[int, int]] = []
    start = prev = clean[0]
    for p in clean[1:]:
        if p == prev + 1:
            prev = p
            continue
        ranges.append((start, prev))
        start = prev = p
    ranges.append((start, prev))

    parts: list[str] = []
    for a, b in ranges:
        if a == b:
            parts.append(str(a))
        else:
            parts.append(f"{a}–{b}")
    return "pp. " + ", ".join(parts)


def _parent_label(std: dict[str, Any]) -> str:
    label = (std.get("label") or "").strip()
    text = (std.get("text") or "").strip()
    if label and text:
        if text.lower().startswith(label.lower()):
            return text
        return f"{label}: {text}"
    return text or label or std.get("code", "")


def _parent_short_name(std: dict[str, Any]) -> str:
    """Example rollup form: ``1.P.EICC.3 — Comprehension Strategies``."""
    code = str(std.get("code") or "").strip()
    label = (std.get("label") or "").strip()
    if not label:
        text = (std.get("text") or "").strip()
        label = text.split(":", 1)[0].strip() if text else ""
        if len(label) > 80:
            label = label[:77] + "…"
    if code and label:
        return f"{code} — {label}"
    return code or label


def _big_idea_heading(std: dict[str, Any], index_in_domain: int) -> str:
    label = (std.get("label") or "").strip()
    text = (std.get("text") or "").strip()
    roman = (
        _ROMAN[index_in_domain]
        if index_in_domain < len(_ROMAN)
        else str(index_in_domain + 1)
    )
    if not label and text:
        label = text.split(":", 1)[0].strip()
    abbr = std.get("code", "").rsplit(".", 1)[-1]
    if label and abbr and abbr.isalpha() and len(abbr) <= 4:
        return f"{roman}. BIG IDEA: {label} ({abbr})"
    if label:
        return f"{roman}. BIG IDEA: {label}"
    return f"{roman}. BIG IDEA: {std.get('code', '')}"


def load_standards(path: Path | str) -> list[dict[str, Any]]:
    p = Path(path)
    data = json.loads(p.read_text(encoding="utf-8"))
    standards = data.get("standards")
    if not isinstance(standards, list) or not standards:
        raise ClientFormatError(f"{p}: missing standards[]")
    return standards


def load_corrected_master(path: Path | str) -> list[dict[str, Any]]:
    p = Path(path)
    wb = load_workbook(p, data_only=True)
    ws = wb.active
    headers = [ws.cell(1, c).value for c in range(1, ws.max_column + 1)]
    if not headers or "standard_code" not in headers or "matched_status" not in headers:
        raise ClientFormatError(f"{p}: expected corrected-master headers")
    rows: list[dict[str, Any]] = []
    for r in range(2, ws.max_row + 1):
        row = {headers[i]: ws.cell(r, i + 1).value for i in range(len(headers))}
        if not row.get("resource_id") or not row.get("standard_code"):
            continue
        rows.append(row)
    if not rows:
        raise ClientFormatError(f"{p}: no data rows")
    return rows


def load_alignment_rows_from_judge_dir(judge_dir: Path | str) -> list[dict[str, Any]]:
    """Load alignment rows from ``output/judge/*.json`` verdicts."""
    root = Path(judge_dir)
    if not root.is_dir():
        raise ClientFormatError(f"{root}: judge dir not found")
    rows: list[dict[str, Any]] = []
    for fp in sorted(root.glob("*.json")):
        try:
            data = json.loads(fp.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as e:
            raise ClientFormatError(f"{fp}: {e}") from e
        rid = (data.get("resource_id") or fp.stem).strip()
        for v in data.get("verdicts") or []:
            code = (v.get("standard_code") or "").strip()
            if not code:
                continue
            rows.append(
                {
                    "resource_id": rid,
                    "standard_code": code,
                    "matched_status": v.get("matched_status"),
                    "evidence_page": v.get("evidence_page"),
                    "rationale": v.get("rationale"),
                    "input_scope_caveat": v.get("input_scope_caveat"),
                    "evidence": v.get("evidence"),
                    "grounded": v.get("grounded"),
                    "confidence": v.get("confidence"),
                    "needs_review": v.get("needs_review"),
                    "prompt_version": v.get("prompt_version")
                    or data.get("prompt_version"),
                }
            )
    if not rows:
        raise ClientFormatError(f"{root}: no judge verdicts found")
    return rows


def load_alignment_rows_from_csv_dir(csv_dir: Path | str) -> list[dict[str, Any]]:
    """Load alignment rows from per-lesson ``output/result/*.csv`` files."""
    root = Path(csv_dir)
    if not root.is_dir():
        raise ClientFormatError(f"{root}: csv dir not found")
    rows: list[dict[str, Any]] = []
    for fp in sorted(root.glob("*.csv")):
        with fp.open(encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if not row.get("resource_id") or not row.get("standard_code"):
                    continue
                rows.append(dict(row))
    if not rows:
        raise ClientFormatError(f"{root}: no CSV alignment rows found")
    return rows


def load_lesson_page_fallback(lessons_dir: Path | str | None) -> dict[str, int]:
    """resource_id → page_start from Stage-1 lesson JSON (fallback only)."""
    out: dict[str, int] = {}
    if lessons_dir is None:
        return out
    root = Path(lessons_dir)
    if not root.is_dir():
        return out
    for f in root.glob("*.json"):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        rid = (data.get("code") or f.stem).strip()
        ps = data.get("page_start")
        if isinstance(ps, int) and ps > 0:
            out[rid] = ps
        elif isinstance(ps, float) and ps > 0:
            out[rid] = int(ps)
    return out


def aggregate_teacher_pages(
    master_rows: list[dict[str, Any]],
    *,
    lesson_page_fallback: dict[str, int] | None = None,
    include_partial: bool = True,
) -> dict[str, dict[str, Any]]:
    """standard_code → {pages, full_n, partial_n, lessons, caveats}."""
    allowed = {"full", "partial"} if include_partial else {"full"}
    fallback = lesson_page_fallback or {}
    by_code: dict[str, dict[str, Any]] = {}

    for row in master_rows:
        status = str(row.get("matched_status") or "").strip().lower()
        if status not in allowed:
            continue
        code = str(row.get("standard_code") or "").strip()
        if not code:
            continue
        bucket = by_code.setdefault(
            code,
            {
                "pages": set(),
                "full_n": 0,
                "partial_n": 0,
                "lessons": set(),
                "caveats": set(),
                "missing_page_lessons": set(),
                "partial_rationales": [],
            },
        )
        if status == "full":
            bucket["full_n"] += 1
        else:
            bucket["partial_n"] += 1
            rat = (row.get("rationale") or "").strip()
            if rat and len(bucket["partial_rationales"]) < 3:
                bucket["partial_rationales"].append(rat)

        rid = str(row.get("resource_id") or "").strip()
        if rid:
            bucket["lessons"].add(rid)

        page = row.get("evidence_page")
        page_i: int | None = None
        if page is not None and str(page).strip() != "":
            try:
                page_i = int(float(page))
            except (TypeError, ValueError):
                page_i = None
        if page_i is None or page_i <= 0:
            page_i = fallback.get(rid)
            if page_i:
                bucket["missing_page_lessons"].add(rid)
            else:
                bucket["missing_page_lessons"].add(rid or "?")
                continue
        bucket["pages"].add(page_i)

        caveat = (row.get("input_scope_caveat") or "").strip()
        if caveat:
            bucket["caveats"].add(caveat)

    return by_code


def _teacher_pages_text(agg: dict[str, Any] | None) -> str:
    if not agg or not agg["pages"]:
        return ""
    return format_page_list(agg["pages"])


def _other_materials_cell(agg: dict[str, Any] | None) -> str:
    """Kept for Excel mirror notes only (Student Materials stays blank in DOCX)."""
    if not agg:
        return ""
    if agg.get("caveats"):
        return (
            "Supporting Materials / Read-aloud Guides were not included in the "
            "provided Teacher Guide PDF; some comprehension alignments may be "
            "understated pending those materials."
        )
    return ""


def _qa_notes_cell(agg: dict[str, Any] | None) -> str:
    """Internal QA notes for the Excel mirror only."""
    if not agg:
        return ""
    notes: list[str] = []
    if agg.get("caveats"):
        notes.append("input_scope_caveat present on one or more lesson rows")
    missing = agg.get("missing_page_lessons") or set()
    if missing:
        notes.append(
            "missing evidence_page lessons (Stage-1 page_start used when available): "
            + ", ".join(sorted(str(x) for x in missing))
        )
    return "; ".join(notes)


def _merge_row_span(row: Any, start: int, end: int) -> Any:
    """Merge cells start..end inclusive; return the surviving cell."""
    return row.cells[start].merge(row.cells[end])


def build_client_docx(
    *,
    standards: list[dict[str, Any]],
    teacher_by_code: dict[str, dict[str, Any]],
    program_name: str,
    grade_label: str = "Grade 1",
    framework_title_lines: list[str] | None = None,
    framework_header: str = "Georgia English Language Arts Standards (2023), Grade 1",
    standards_column_header: str = "Georgia’s English Language Arts Standards",
    guide_label: str = "Module 2",
    parent_rollups: dict[str, dict[str, Any]] | None = None,
) -> Document:
    title_lines = framework_title_lines or [
        "Georgia’s",
        "K–12 English Language Arts Standards*",
    ]
    rollups = parent_rollups or {}
    doc = Document()
    for section in doc.sections:
        section.top_margin = Inches(0.75)
        section.bottom_margin = Inches(0.75)
        section.left_margin = Inches(0.75)
        section.right_margin = Inches(0.75)

    _configure_continuing_page_header(
        doc,
        program_name=program_name,
        framework_header=framework_header,
    )
    _add_title_page(
        doc,
        program_name=program_name,
        grade_label=grade_label,
        framework_title_lines=title_lines,
    )

    table = doc.add_table(rows=1, cols=4)
    table.style = "Table Grid"
    table.autofit = True

    hdr = table.rows[0]
    standards_hdr = _merge_row_span(hdr, 0, 1)
    _set_cell_text(
        standards_hdr,
        standards_column_header,
        bold=True,
        center=True,
    )
    _set_cell_shading(standards_hdr, _GRAY)
    _set_cell_text(hdr.cells[2], "Teacher’s Guide", bold=True, center=True)
    _set_cell_shading(hdr.cells[2], _GRAY)
    _set_cell_text(hdr.cells[3], "Other Materials", bold=True, center=True)
    _set_cell_shading(hdr.cells[3], _GRAY)

    domain_bi_index: dict[str, int] = defaultdict(int)

    for std in standards:
        level = std.get("level")
        code = std.get("code") or ""

        if level == "domain":
            row = table.add_row()
            cell = _merge_row_span(row, 0, 3)
            text = DOMAIN_DISPLAY.get(code, (std.get("label") or code).upper())
            _set_cell_text(cell, text, bold=True)
            _set_cell_shading(cell, _GRAY)
            continue

        if level == "big_idea":
            parent = std.get("parent_code") or ""
            idx = domain_bi_index[parent]
            domain_bi_index[parent] = idx + 1
            heading = _big_idea_heading(std, idx)

            row = table.add_row()
            cell = _merge_row_span(row, 0, 3)
            _set_cell_text(cell, heading, bold=True)

            desc_row = table.add_row()
            desc_cell = _merge_row_span(desc_row, 0, 3)
            _set_cell_text(desc_cell, (std.get("text") or "").strip(), bold=False)
            continue

        if level == "standard":
            row = table.add_row()
            label = _parent_label(std)
            _set_cell_text(row.cells[0], code, bold=False)
            rollup = rollups.get(code) or {}
            statement = (rollup.get("statement") or "").strip()
            # Fixed client layout: merge cols 1–3; full parent text in one row block.
            body = f"{label}\n{statement}" if statement else label
            merged = _merge_row_span(row, 1, 3)
            _set_multiline_cell(merged, body.split("\n"))
            continue

        if level == "substandard":
            row = table.add_row()
            agg = teacher_by_code.get(code)
            _set_cell_text(row.cells[0], code, bold=False)
            _set_cell_text(row.cells[1], (std.get("text") or "").strip(), bold=False)
            _fill_leaf_material_cells(
                row.cells[2],
                row.cells[3],
                agg,
                guide_label=guide_label,
            )
            continue

        row = table.add_row()
        _set_cell_text(row.cells[0], code)
        label_cell = _merge_row_span(row, 1, 3)
        _set_cell_text(label_cell, _parent_label(std))

    foot = doc.add_paragraph()
    fr = foot.add_run(
        f"* Alignments drawn from {program_name} Teacher Guide ({guide_label}) only. "
        "Other Materials are blank when Supporting Materials were not in the provided input. "
        "Parent rows open with the skill title, then skill-named roll-up or beyond-scope prose."
    )
    _style_run(fr, bold=False)
    fr.font.size = Pt(8)
    return doc


def build_client_xlsx_mirror(
    *,
    standards: list[dict[str, Any]],
    teacher_by_code: dict[str, dict[str, Any]],
    program_name: str,
    guide_label: str = "Module 2",
    parent_rollups: dict[str, dict[str, Any]] | None = None,
    source_label: str = "judge",
) -> Workbook:
    """Flat QA mirror + parent Rollup sheet (client skill wording)."""
    rollups = parent_rollups or {}
    wb = Workbook()
    ws = wb.active
    ws.title = "Client_correlation"
    prefix = f"{guide_label}:"
    ws.append(
        [
            "standard_code",
            "level",
            "standard_text",
            "teacher_guide_pages",
            "full_count",
            "partial_count",
            "lessons",
            "other_materials_note",
            "qa_notes",
        ]
    )
    for std in standards:
        code = std.get("code") or ""
        level = std.get("level") or ""
        if level != "substandard":
            continue
        agg = teacher_by_code.get(code)
        pages = format_page_list(agg["pages"]) if agg else ""
        beyond = _beyond_scope_note(guide_label)
        if not pages:
            tg_note = beyond
        elif (
            agg
            and int(agg.get("partial_n") or 0) > 0
            and int(agg.get("full_n") or 0) == 0
        ):
            expl = _short_partial_explanation(list(agg.get("partial_rationales") or []))
            note_line = f"{_PARTIAL_NOTE} {expl}".strip() if expl else _PARTIAL_NOTE
            tg_note = f"{note_line}\n{prefix} {pages}"
        else:
            tg_note = f"{prefix} {pages}"
        ws.append(
            [
                code,
                level,
                (std.get("text") or "").strip(),
                tg_note,
                agg.get("full_n", 0) if agg else 0,
                agg.get("partial_n", 0) if agg else 0,
                ", ".join(sorted(agg["lessons"])) if agg else "",
                beyond if not pages else _other_materials_cell(agg),
                _qa_notes_cell(agg),
            ]
        )

    std_by_code = {
        str(s.get("code") or "").strip(): s
        for s in standards
        if s.get("code")
    }

    roll = wb.create_sheet("Parent_rollup")
    # Match Rollup_Format_Example_for_Engineer.xlsx columns (client target only).
    roll.append(
        [
            "Standard Section",
            "Parent Standard",
            "Alignment",
            "Roll-up statement — CLIENT FORMAT (target)",
        ]
    )
    for parent_code in sorted(rollups.keys()):
        r = rollups[parent_code]
        align = r.get("alignment") or ""
        align_label = {
            "partially_met": "Partially met",
            "fully_met": "Fully met",
            "beyond_scope": "Beyond scope",
        }.get(align, align)
        parent_std = std_by_code.get(parent_code) or {
            "code": parent_code,
            "label": r.get("parent_label") or "",
        }
        roll.append(
            [
                r.get("section") or domain_section_for_code(parent_code),
                _parent_short_name(parent_std),
                align_label,
                r.get("statement") or "",
            ]
        )

    meta = wb.create_sheet("provenance")
    meta.append(["field", "value"])
    meta.append(["client_format_version", CLIENT_FORMAT_VERSION])
    meta.append(["program_name", program_name])
    meta.append(["guide_label", guide_label])
    meta.append(["source", source_label])
    meta.append(["include_statuses", "full,partial"])
    cited = sum(1 for a in teacher_by_code.values() if a.get("pages"))
    meta.append(["leaf_standards_with_citations", cited])
    meta.append(
        [
            "leaf_standards_total",
            sum(1 for s in standards if s.get("level") == "substandard"),
        ]
    )
    meta.append(
        [
            "parents_partially_met",
            sum(1 for r in rollups.values() if r.get("alignment") == "partially_met"),
        ]
    )
    return wb


def write_client_correlation_package(
    *,
    standards_json: Path | str,
    out_docx: Path | str,
    out_xlsx: Path | str | None = None,
    master_xlsx: Path | str | None = None,
    judge_dir: Path | str | None = None,
    csv_dir: Path | str | None = None,
    lessons_dir: Path | str | None = None,
    program_name: str = "EL Education Curriculum",
    guide_label: str = "Module 2",
    include_partial: bool = True,
    grade_label: str = "Grade 1",
    framework_title_lines: list[str] | None = None,
    framework_header: str = "Georgia English Language Arts Standards (2023), Grade 1",
    standards_column_header: str = "Georgia’s English Language Arts Standards",
) -> dict[str, Any]:
    """Build DOCX + XLSX from judge / CSV / corrected-master rows.

    Prefer ``judge_dir`` (post-judge) or ``csv_dir`` (post report / result CSVs).
    ``master_xlsx`` remains available for hand-corrected delivery sheets.
    """
    standards = load_standards(standards_json)
    source_label = "unknown"
    if judge_dir:
        master_rows = load_alignment_rows_from_judge_dir(judge_dir)
        source_label = f"judge:{judge_dir}"
    elif csv_dir:
        master_rows = load_alignment_rows_from_csv_dir(csv_dir)
        source_label = f"csv:{csv_dir}"
    elif master_xlsx:
        master_rows = load_corrected_master(master_xlsx)
        source_label = f"master:{master_xlsx}"
    else:
        raise ClientFormatError(
            "provide one of: judge_dir, csv_dir, or master_xlsx"
        )

    fallback = load_lesson_page_fallback(lessons_dir)
    teacher_by_code = aggregate_teacher_pages(
        master_rows,
        lesson_page_fallback=fallback,
        include_partial=include_partial,
    )
    parent_rollups = build_parent_rollups(
        standards, teacher_by_code, guide_label=guide_label
    )

    doc = build_client_docx(
        standards=standards,
        teacher_by_code=teacher_by_code,
        program_name=program_name,
        grade_label=grade_label,
        framework_title_lines=framework_title_lines,
        framework_header=framework_header,
        standards_column_header=standards_column_header,
        guide_label=guide_label,
        parent_rollups=parent_rollups,
    )
    out_doc_path = Path(out_docx)
    out_doc_path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(out_doc_path)

    xlsx_path = None
    if out_xlsx is not None:
        wb = build_client_xlsx_mirror(
            standards=standards,
            teacher_by_code=teacher_by_code,
            program_name=program_name,
            guide_label=guide_label,
            parent_rollups=parent_rollups,
            source_label=source_label,
        )
        xlsx_path = Path(out_xlsx)
        xlsx_path.parent.mkdir(parents=True, exist_ok=True)
        wb.save(xlsx_path)

    cited = sum(1 for a in teacher_by_code.values() if a.get("pages"))
    partial_parents = sum(
        1 for r in parent_rollups.values() if r.get("alignment") == "partially_met"
    )
    summary = {
        "schema_version": CLIENT_FORMAT_VERSION,
        "program_name": program_name,
        "guide_label": guide_label,
        "source": source_label,
        "alignment_rows": len(master_rows),
        "positive_standards_cited": cited,
        "parents_partially_met": partial_parents,
        "docx": str(out_doc_path),
        "xlsx": str(xlsx_path) if xlsx_path else None,
        "include_partial": include_partial,
        "lesson_page_fallback_keys": len(fallback),
    }
    summary_path = out_doc_path.with_suffix(".summary.json")
    atomic_write_text(summary_path, json.dumps(summary, indent=2) + "\n")
    summary["summary_path"] = str(summary_path)
    return summary


__all__ = [
    "CLIENT_FORMAT_VERSION",
    "ClientFormatError",
    "aggregate_teacher_pages",
    "build_parent_rollups",
    "format_page_list",
    "load_alignment_rows_from_csv_dir",
    "load_alignment_rows_from_judge_dir",
    "skill_phrase",
    "write_client_correlation_package",
]
