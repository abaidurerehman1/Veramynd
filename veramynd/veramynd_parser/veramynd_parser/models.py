"""Typed data contracts for the Veramynd parser.

Every stage of the pipeline consumes and produces these Pydantic models. They are
the interface between stages — a stage that returns one of these has, by
construction, produced a shape the next stage can rely on.

Vocabulary note: the teacher guide declares standards in one framework (e.g. CCSS
codes like ``RL.1.1``) while the target standards spreadsheet uses another (e.g.
Georgia codes like ``1.F.PA.4.d``). These models deliberately keep the two apart:
``Lesson.declared_standards`` holds the publisher's *claim*, and the standards tree
holds the *target framework*. Nothing here collapses one into the other.
"""

from __future__ import annotations

import re
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from . import text_utils as tu

# Reject unknown fields loudly on every domain contract, matching the pattern
# Config already uses (config.py). Without this, a stale/renamed field on a
# schema change silently round-trips through old JSON (extra keys dropped,
# missing keys defaulted) instead of raising -- see normalize/cache.py's
# content-addressing, which this directly protects.
_STRICT = ConfigDict(extra="forbid")

# Sub-block letters are always single uppercase ASCII (A, B, C, ...) -- the
# grammar both dividers parse against (_SUBBLOCK in docling_divider.py,
# AGENDA_ITEM in text_utils.py). Anything else means a caller built the model
# directly with bad data, not a real parse.
_LETTER_PATTERN = r"^[A-Z]$"


def _check_codes_well_formed(codes: list[str], field_name: str) -> list[str]:
    bad = [c for c in codes if not tu.STANDARD_CODE.fullmatch(c)]
    if bad:
        raise ValueError(f"{field_name}: malformed standard code(s): {bad}")
    return codes


# --------------------------------------------------------------------------- #
# Provenance
# --------------------------------------------------------------------------- #
class Provenance(BaseModel):
    """Where a piece of content came from in the source document."""

    model_config = _STRICT

    source_id: str = Field(description="Stable id of the source file (name or hash).")
    page_start: int | None = Field(default=None, description="1-indexed first page.")
    page_end: int | None = Field(default=None, description="1-indexed last page.")
    sheet: str | None = Field(default=None, description="Worksheet name, for spreadsheets.")
    row: int | None = Field(default=None, description="1-indexed row, for spreadsheets.")


# --------------------------------------------------------------------------- #
# Teacher-guide lessons
# --------------------------------------------------------------------------- #
class BlockFamily(str, Enum):
    """The three structural roles a lesson block can play."""

    COVER = "cover"                # the publisher's claim: standards, targets, agenda
    TEACHING_NOTES = "teaching_notes"  # context: purpose, vocabulary, materials
    INSTRUCTIONAL = "instructional"    # evidence: publisher section blocks + steps


class AgendaItem(BaseModel):
    """One timed sub-block from a lesson's Agenda (e.g. 'Work Time C, 15 minutes')."""

    model_config = _STRICT

    section: str = Field(
        description=(
            "Publisher section label from Stage-1 (e.g. Opening, Warm-Up, Guided Practice)."
        )
    )
    letter: str = Field(description="Sub-block letter, e.g. 'A'.", pattern=_LETTER_PATTERN)
    title: str = Field(default="", description="Activity title.")
    minutes: int | None = Field(default=None, ge=0, description="Duration in minutes, if printed.")


class LearningTarget(BaseModel):
    """A 'I can ...' statement, with the standard codes the publisher tagged to it."""

    model_config = _STRICT

    text: str
    codes: list[str] = Field(default_factory=list, description="Declared standard codes (framework of the guide).")

    @field_validator("codes")
    @classmethod
    def _codes_well_formed(cls, v: list[str]) -> list[str]:
        return _check_codes_well_formed(v, "LearningTarget.codes")


class InstructionalStep(BaseModel):
    """One instructional step with the page its text actually appears on."""

    model_config = _STRICT

    text: str
    page: int = Field(
        default=0,
        ge=0,
        description=(
            "Page this step's text appears on. 0 means unknown — used for legacy "
            "JSON that only stored the block start page, and for unmatched blocks."
        ),
    )

    @model_validator(mode="before")
    @classmethod
    def _coerce_plain_string(cls, value: object) -> object:
        if isinstance(value, str):
            return {"text": value, "page": 0}
        return value


class InstructionalBlock(BaseModel):
    """One lettered instructional sub-block (e.g. Work Time A) with its steps.

    ``steps`` is the actual procedure — what the teacher and students do — extracted
    from the lesson body. This is the evidence-bearing content: the downstream
    alignment judge reads these steps to decide what a lesson teaches, and the
    grounding check quotes from them. The agenda (on the cover) is the plan; this is
    the execution. Each step keeps the page its own lines came from, so a block
    that runs 20 lines on page 45 and 10 on page 46 reports both pages with that
    content rather than only the start page.
    """

    model_config = _STRICT

    section: str = Field(
        description=(
            "Publisher section label from Stage-1 (e.g. Opening, Warm-Up, Guided Practice)."
        )
    )
    letter: str = Field(description="Sub-block letter, e.g. 'A'.", pattern=_LETTER_PATTERN)
    title: str = Field(default="", description="Activity title, from the body header.")
    minutes: int | None = Field(default=None, ge=0)
    page: int = Field(
        ge=0,
        description=(
            "Page the sub-block starts on. Sentinel: 0 means division never located "
            "this block's title in the lesson body (an agenda-only placeholder that "
            "still needs its content filled in) -- verifier check V13 treats page == 0 "
            "as 'unmatched'. A real page is always >= 1. (0 is the ONLY value below 1 "
            "this field ever legitimately takes -- see docs/complete-project-flow.md "
            "section 9.6.) Per-line pages live on ``steps``."
        ),
    )
    steps: list[InstructionalStep] = Field(
        default_factory=list,
        description="Instructional steps (teacher & student actions), each with its page.",
    )

    @model_validator(mode="after")
    def _inherit_block_page_for_legacy_steps(self) -> "InstructionalBlock":
        # Old Stage-1 JSON stored steps as bare strings. After coercion those
        # steps have page=0; fill them from the block start page so consumers
        # still have a page, while newly extracted steps keep their own pages.
        if self.page <= 0 or not self.steps:
            return self
        if all(step.page == 0 for step in self.steps):
            self.steps = [
                step.model_copy(update={"page": self.page}) for step in self.steps
            ]
        return self

    @property
    def step_texts(self) -> list[str]:
        return [step.text for step in self.steps]

    def steps_grouped_by_page(self) -> list[tuple[int, list[str]]]:
        """Consecutive steps grouped by the page their text appears on."""
        groups: list[tuple[int, list[str]]] = []
        for step in self.steps:
            text = (step.text or "").strip()
            if not text:
                continue
            page = step.page if step.page else self.page
            if groups and groups[-1][0] == page:
                groups[-1][1].append(text)
            else:
                groups.append((page, [text]))
        return groups


def format_instructional_block_text(
    *,
    section: str,
    letter: str,
    title: str = "",
    steps: list[InstructionalStep] | None = None,
    block_page: int = 0,
) -> str:
    """Render a block with ``(page N)`` on each page the content occupies."""
    header_base = f"[{section} {letter}] {title}".strip()
    entries: list[tuple[str, int]] = []
    for step in steps or []:
        text = (step.text or "").strip()
        if not text:
            continue
        page = step.page if step.page else block_page
        entries.append((text, page))

    if not entries:
        return header_base

    parts: list[str] = []
    current_page: int | None = None
    for text, page in entries:
        if page and page != current_page:
            parts.append(f"{header_base} (page {page})")
            current_page = page
        elif not parts:
            if page:
                parts.append(f"{header_base} (page {page})")
                current_page = page
            else:
                parts.append(header_base)
        parts.append(f"- {text}")
    return "\n".join(parts)


class Table(BaseModel):
    """A structured table recovered by Docling's TableFormer.

    Tables (materials lists, vocabulary grids, assessment checklists) carry their
    cells row-major, so downstream stages get real structure rather than a flattened
    token stream. Recovering these is the primary reason Docling is the main engine.
    """

    model_config = _STRICT

    page: int
    n_rows: int
    n_cols: int
    cells: list[list[str]] = Field(default_factory=list, description="Row-major cell text.")
    provenance: Provenance | None = None

    @model_validator(mode="after")
    def _check_shape(self) -> "Table":
        # The real extraction path (docling_divider.tables()) always derives n_rows/
        # n_cols FROM cells, so this can only fire for a caller constructing a Table
        # directly with an inconsistent shape -- exactly the gap this closes.
        if len(self.cells) != self.n_rows:
            raise ValueError(
                f"Table.n_rows={self.n_rows} but cells has {len(self.cells)} row(s)"
            )
        for i, row in enumerate(self.cells):
            if len(row) != self.n_cols:
                raise ValueError(
                    f"Table.n_cols={self.n_cols} but row {i} has {len(row)} cell(s)"
                )
        return self


_G_M_U_L = re.compile(r"^G(\d+)M(\d+)U(\d+)L(\d+)$")


class Lesson(BaseModel):
    """One lesson extracted from a teacher guide."""

    model_config = _STRICT

    code: str = Field(description="Full identity, e.g. 'G1M2U1L1'.")
    grade: int = Field(ge=0)
    module: int = Field(ge=0)
    unit: int = Field(ge=0)
    lesson: int = Field(ge=0)
    title: str = ""
    page_start: int = Field(ge=1)
    page_end: int = Field(ge=1)
    declared_standards: list[str] = Field(
        default_factory=list,
        description="Standards the lesson CLAIMS to target (guide's framework, unverified).",
    )

    @field_validator("declared_standards")
    @classmethod
    def _declared_standards_well_formed(cls, v: list[str]) -> list[str]:
        return _check_codes_well_formed(v, "Lesson.declared_standards")
    learning_targets: list[LearningTarget] = Field(default_factory=list)
    agenda: list[AgendaItem] = Field(default_factory=list, description="Cover ToC: the plan.")
    instructional_blocks: list[InstructionalBlock] = Field(
        default_factory=list, description="Body: the sub-blocks with their steps (the content).")
    materials: list[str] = Field(default_factory=list, description="Materials list items.")
    vocabulary: list[str] = Field(default_factory=list, description="Vocabulary terms (New + Review).")
    tables: list[Table] = Field(default_factory=list, description="Genuine (≥2-column) tables (Docling).")
    parsed_by: str = Field(default="docling", description="Primary engine that produced this lesson.")
    provenance: Provenance | None = None

    @property
    def page_count(self) -> int:
        return self.page_end - self.page_start + 1

    @property
    def total_minutes(self) -> int | None:
        mins = [a.minutes for a in self.agenda if a.minutes is not None]
        return sum(mins) if mins else None

    @model_validator(mode="after")
    def _check_invariants(self) -> "Lesson":
        # Real spans are pre-validated by separator.py before a Lesson is ever built
        # from them, so this can only fire for a caller constructing/mutating a
        # Lesson directly (a test, a future ingestion adapter) -- it never fires on
        # the real parse path, and does not run on later attribute mutation (no
        # validate_assignment), so the verifier's own "corrupt a real Lesson, then
        # confirm verify() catches it" tests are unaffected.
        if self.page_end < self.page_start:
            raise ValueError(
                f"Lesson {self.code}: page_end ({self.page_end}) < page_start "
                f"({self.page_start})"
            )
        m = _G_M_U_L.match(self.code)
        if m:
            g, mo, u, le = (int(x) for x in m.groups())
            if (g, mo, u, le) != (self.grade, self.module, self.unit, self.lesson):
                raise ValueError(
                    f"Lesson code {self.code!r} does not match its grade/module/unit/"
                    f"lesson fields ({self.grade}/{self.module}/{self.unit}/{self.lesson})"
                )
        return self


class Unit(BaseModel):
    """A unit within a module — a grouping of lessons, preceded by an overview."""

    model_config = _STRICT

    unit: int = Field(ge=0)
    overview_page_start: int | None = Field(default=None, ge=1)
    overview_page_end: int | None = Field(default=None, ge=1)
    lessons: list[Lesson] = Field(default_factory=list)


class TeacherGuide(BaseModel):
    """The parsed teacher guide: the module, its units, and all its lessons.

    Deliberately does **not** enforce cross-lesson invariants (unique codes, page
    coverage, contiguity) at construction time -- those are the safety-net
    verifier's job (``verify/verifier.py``), by design: parsing and checking are
    separate stages so a structurally bad parse can be constructed, then reported
    as a loud, quarantined BLOCK rather than crashing mid-parse. See
    ``docs/architecture.md``'s "fail loud, never silently" principle.
    """

    model_config = _STRICT

    source_id: str
    grade: int = Field(ge=0)
    module: int = Field(ge=0)
    page_count: int = Field(ge=1)
    engine: str = Field(default="docling", description="Primary content engine used.")
    ocr_used: bool = Field(default=False, description="Whether OCR ran during parsing.")
    units: list[Unit] = Field(default_factory=list)
    separation_fallback_reason: str | None = Field(
        default=None,
        description=(
            "Set when bookmark-based separation raised and the parser fell back to "
            "font/running-header separation for the whole document -- surfaces the "
            "SeparationError's own diagnosis instead of discarding it silently."
        ),
    )
    engine_fallback_reason: str | None = Field(
        default=None,
        description=(
            "Set when the Docling content engine failed (whole document or a "
            "specific lesson span) and PyMuPDF was used instead. None when "
            "engine='docling' ran clean, or when engine='pymupdf' was requested "
            "directly (no fallback involved)."
        ),
    )

    @property
    def lessons(self) -> list[Lesson]:
        return [lesson for unit in self.units for lesson in unit.lessons]


# --------------------------------------------------------------------------- #
# Standards framework (from the spreadsheet)
# --------------------------------------------------------------------------- #
class StandardLevel(str, Enum):
    """Hierarchy level of a standards-framework item, derived from code depth."""

    DOMAIN = "domain"            # 1.F
    BIG_IDEA = "big_idea"        # 1.F.PA
    STANDARD = "standard"        # 1.F.PA.4
    SUBSTANDARD = "substandard"  # 1.F.PA.4.d


class Standard(BaseModel):
    """One node in the standards tree."""

    model_config = _STRICT

    code: str = Field(description="e.g. '1.F.PA.4.d'.")
    level: StandardLevel
    label: str = Field(default="", description="Short prefix label, e.g. 'Syllables'.")
    text: str = Field(default="", description="Full standard text.")
    parent_code: str | None = None
    grade: int | None = None
    provenance: Provenance | None = None


class GradeStandards(BaseModel):
    """The full standards framework for one grade, as a flat, parent-linked list.

    The tree structure is fully recoverable from ``parent_code`` links; a flat list
    keeps the contract simple and identical regardless of source (spreadsheet, API,
    or knowledge graph).
    """

    model_config = _STRICT

    grade: int
    framework: str = Field(default="", description="e.g. 'GA ELA'.")
    standards: list[Standard] = Field(default_factory=list)

    def by_level(self, level: StandardLevel) -> list[Standard]:
        return [s for s in self.standards if s.level == level]

    def children_of(self, code: str) -> list[Standard]:
        return [s for s in self.standards if s.parent_code == code]
