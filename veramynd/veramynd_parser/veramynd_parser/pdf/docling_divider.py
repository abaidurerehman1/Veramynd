"""Lesson division from Docling's semantic structure.

Where the PyMuPDF divider infers roles from font size, this one reads the roles
Docling already assigned: a lesson's parts are ``section_header`` elements, its
content is the ``list_item`` elements beneath them, and its tables come straight from
TableFormer. This is more robust — no font thresholds to tune — and it recovers the
tables the font path cannot.

Section grammar within a lesson (all as Docling ``section_header`` text):

    Lesson N: <title>
    CCS Standards            -> declared standards (list_items below)
    Daily Learning Target(s) -> learning targets  (list_items below)
    Agenda
      1. Opening             -> agenda items (list_items below, letters A/B/… by order)
      2. Work Time
      3. Closing and Assessment
    Teaching Notes ...
    Opening / Work Time / Closing and Assessment  (body majors, no leading number)
"""

from __future__ import annotations

import re
from enum import Enum, auto

from .. import text_utils as tu
from ..config import Config
from ..models import AgendaItem, InstructionalBlock, LearningTarget, Lesson, Provenance, Table
from .division import fill_steps
from .docling_parser import DoclingParse, Element
from .separator import LessonSpan

# a numbered agenda section header, e.g. "1. Opening", "2.  Work Time"
_AGENDA_SECTION = re.compile(r"^\d+\.\s*(.+)$")
# a lettered body sub-block header, e.g. "A. Reading Aloud: … (10 minutes)"
_SUBBLOCK = re.compile(r"^([A-Z])\.\s+(.+)$")


class _AgendaPhase(Enum):
    """The full state space of :meth:`_DoclingDivider.agenda`'s scan."""

    OUTSIDE = auto()    # before the 'Agenda' header, or after it definitively ended
    IN_AGENDA = auto()  # between 'Agenda' and the next genuine non-agenda header


def _clean(text: str) -> str:
    return tu.clean_line(tu.stitch_wrapped_minutes(tu.dehyphenate(text)))


# vocabulary sub-headers used by _collect_vocabulary / header detection
_ALL_SECTION_NAMES = frozenset({
    "Key:", "New:", "Review:", "Teaching Notes", "Opening", "Work Time",
    "Closing and Assessment",
})


class _DoclingDivider:
    def __init__(self, docling: DoclingParse, span: LessonSpan, cfg: Config):
        self.cfg = cfg
        self.span = span
        self.source_id = docling.source_id
        self.elements: list[Element] = docling.elements_in_range(span.page_start, span.page_end)
        self._raw_tables = docling.tables_in_range(span.page_start, span.page_end)

    def _is_section(self, text: str) -> bool:
        return any(text.startswith(h) for h in self.cfg.section_headers)

    def _is_header_text(self, text: str) -> bool:
        return (text in _ALL_SECTION_NAMES) or self._is_section(text)

    def _lines(self) -> list[tuple[str, str]]:
        """Unified (kind, text) sequence over elements AND flattened 1-column tables.

        Docling sometimes mis-detects a bulleted section (Materials/Vocabulary) as a
        1-column table. Flattening those cells into the same (header|item) stream lets
        one extractor handle both the list-item lessons and the table-absorbed ones.
        Genuine (≥2-column) tables are left alone — see :meth:`tables`.
        """
        # Trust Docling's own section_header label, but also fall back to our own
        # text-based header detection — Docling doesn't always tag a run-in label
        # (e.g. 'Key:') as section_header, and without this a mislabeled 'Key:'
        # would collect straight into materials/vocabulary as if it were content.
        lines: list[tuple[str, str]] = []
        for el in self.elements:
            text = _clean(el.text)
            is_header = el.label == "section_header" or self._is_header_text(text)
            lines.append(("header" if is_header else "item", text))
        for tb in self._raw_tables:
            if tb.n_cols != 1:
                continue  # a real table, not a mis-detected list
            for row in tb.cells:
                text = _clean(row[0]) if row else ""
                if not text or text == "0":
                    continue
                lines.append(("header" if self._is_header_text(text) else "item", text))
        return lines

    def _collect_under(self, headers: tuple[str, ...]) -> list[str]:
        """Items directly under any of ``headers``, stopping at the next section."""
        out: list[str] = []
        collecting = False
        for kind, text in self._lines():
            if kind == "header":
                collecting = text in headers or any(text.startswith(h) for h in headers)
            elif collecting:
                if tu.is_page_furniture(text):
                    continue
                out.append(text)
        return out

    def _collect_vocabulary(self) -> list[str]:
        """New/Review vocab terms with section preserved; skip legend/furniture/prep.

        Emits plain new terms and ``Review: <term>`` for review terms so the
        normalize stamp can split without losing the source New vs Review split.
        """
        from veramynd_parser.normalize.identity_fields import is_prep_or_tip_noise

        out: list[str] = []
        collecting = False
        section: str | None = None  # "new" | "review"
        stop = set(self.cfg.section_headers) | set(self.cfg.instructional_sections)
        stop |= {"Teaching Notes", "Materials", "Opening", "Work Time", "Closing and Assessment"}
        legend = ("Key:", "(L):", "(T):", "(W):")

        for kind, text in self._lines():
            if kind == "header":
                if text == "Vocabulary" or text.startswith("Vocabulary"):
                    collecting = True
                    section = None
                    continue
                if not collecting:
                    continue
                if text in stop or any(text.startswith(h) for h in self.cfg.section_headers):
                    if text not in ("New:", "Review:", "Key:"):
                        collecting = False
                        continue
                if text == "New:" or text.startswith("New:"):
                    section = "new"
                    rest = text[len("New:") :].strip() if text.startswith("New:") else ""
                    if rest and rest != "N/A" and not tu.is_page_furniture(rest):
                        out.append(rest)
                    continue
                if text == "Review:" or text.startswith("Review:"):
                    section = "review"
                    rest = text[len("Review:") :].strip() if text.startswith("Review:") else ""
                    if rest and rest != "N/A" and not tu.is_page_furniture(rest):
                        out.append(f"Review: {rest}")
                    continue
                if text in legend or text.startswith(legend):
                    continue
                collecting = False
                continue

            if not collecting:
                continue
            if text in ("N/A", "Key:") or text.startswith(legend):
                continue
            if text in ("New:", "Review:"):
                section = "new" if text == "New:" else "review"
                continue
            if tu.is_page_furniture(text) or tu.is_prep_or_tip_noise(text):
                continue
            if section == "review":
                out.append(f"Review: {text}" if not text.lower().startswith("review:") else text)
            else:
                out.append(text)
        return out

    # -- fields ----------------------------------------------------------- #
    def title(self) -> str:
        for el in self.elements:
            if el.label == "section_header":
                text = _clean(el.text)
                if text.startswith("Lesson") and not text.startswith("Grade"):
                    return text
        return ""

    def declared_standards(self) -> list[str]:
        # Kept in the order the guide lists them, not alphabetized — the
        # publisher's own ordering is meaningful (see
        # text_utils.dedupe_preserve_order).
        return tu.dedupe_preserve_order(self._codes_under("CCS Standards"))

    def _codes_under(self, header: str) -> list[str]:
        codes: list[str] = []
        collecting = False
        # Body majors / Teaching Notes are not always labeled section_header by
        # Docling; stop on known cover/body boundaries the way PyMuPDF does.
        stop_texts = set(self.cfg.section_headers) | set(self.cfg.instructional_sections)
        stop_texts.add("Teaching Notes")
        for el in self.elements:
            text = _clean(el.text)
            if el.label == "section_header":
                if text == header:
                    collecting = True
                    continue
                if collecting and (self._is_section(text) or text in stop_texts):
                    break
            elif collecting and text in stop_texts:
                # e.g. 'Teaching Notes' / 'Opening' arriving as list_item or text
                break
            # Docling labels a lone item under a section as `text` rather than
            # `list_item` (the same quirk worked around in `agenda()`) — a
            # lesson with exactly one declared standard would otherwise be
            # silently dropped.
            if collecting and el.label in ("list_item", "text"):
                codes.extend(tu.STANDARD_CODE.findall(text))
        return codes

    def learning_targets(self) -> list[LearningTarget]:
        targets: list[LearningTarget] = []
        collecting = False
        for el in self.elements:
            text = _clean(el.text)
            if el.label == "section_header":
                if text.startswith("Daily Learning Target"):
                    collecting = True
                    continue
                if collecting and self._is_section(text):
                    break
            # See _codes_under: a lone target can arrive as `text`, not `list_item`.
            if collecting and el.label in ("list_item", "text") and text.startswith("I can"):
                targets.append(
                    LearningTarget(
                        text=tu.strip_trailing_codes(text),
                        codes=tu.extract_standard_codes(text),
                    )
                )
        return targets

    def agenda(self) -> list[AgendaItem]:
        """Walk this lesson's elements and recover its timed agenda sub-blocks.

        Modeled as an explicit 2-phase state machine (OUTSIDE / IN_AGENDA) instead
        of a boolean flag threaded through nested ifs. The previous shape made
        every new Docling labeling quirk another special-cased branch bolted onto
        the same function, with no way to answer "what are all the states, and is
        every transition covered?" This version answers that directly: every
        (phase, element) case the loop can see is handled explicitly below, and
        the characterization tests in test_docling_divider_robustness.py pin down
        one case per transition.
        """
        items: list[AgendaItem] = []
        phase = _AgendaPhase.OUTSIDE
        section: str | None = None
        letter = ord("A")

        def emit(text: str) -> None:
            nonlocal letter
            mins = tu.MINUTES.search(text)
            # Prefer the printed letter (A./B.) when present — sequential A++
            # discarded publisher letters and drifted from the body headers.
            stamped = tu.AGENDA_ITEM.match(text) or _SUBBLOCK.match(text)
            if stamped:
                used = stamped.group(1)
                title = tu.MINUTES.sub("", stamped.group(2)).strip()
            else:
                used = chr(letter)
                title = re.sub(r"^[A-Z]\.\s*", "", tu.MINUTES.sub("", text).strip())
            items.append(
                AgendaItem(
                    section=section,
                    letter=used,
                    title=title,
                    minutes=int(mins.group(1)) if mins else None,
                )
            )
            letter = ord(used) + 1

        def start_section(canon: str) -> None:
            nonlocal section, letter
            section = canon
            letter = ord("A")

        for el in self.elements:
            text = _clean(el.text)

            # The 'Agenda' header transitions to IN_AGENDA regardless of current
            # phase — a stray duplicate mid-scan is a harmless re-affirmation, not
            # a state to special-case away.
            if el.label == "section_header" and text == "Agenda":
                phase = _AgendaPhase.IN_AGENDA
                continue

            if phase is _AgendaPhase.OUTSIDE:
                continue

            if el.label == "section_header":
                numbered = _AGENDA_SECTION.match(text)
                canon = tu.canonical_agenda_section(numbered.group(1).strip()) if numbered else None
                if canon:
                    start_section(canon)
                elif section and _SUBBLOCK.match(text):
                    # Docling mislabeled a lettered sub-block header (e.g.
                    # 'B. Independent Writing (15 minutes)') as a section_header
                    # instead of a list_item/text — treat it as a normal agenda
                    # item rather than ending the agenda on it.
                    emit(text)
                else:
                    # a genuine non-numbered, non-lettered section header ends the
                    # agenda (e.g. Teaching Notes)
                    phase = _AgendaPhase.OUTSIDE
                    section = None
                continue

            if el.label not in ("list_item", "text"):
                continue

            # Docling labels agenda entries inconsistently: multi-item sections come
            # as `list_item`, a lone item as `text`, and sometimes a bare section
            # name ('Opening', 'Closing and Assessment') itself arrives as a
            # `list_item` rather than a numbered `section_header`.
            bare = tu.canonical_agenda_section(text)
            if bare and not tu.MINUTES.search(text) and len(text) <= 25:
                start_section(bare)
            elif section:
                emit(text)

        return items

    def instructional_blocks(self) -> list[InstructionalBlock]:
        """The body sub-blocks (Opening/Work Time/Closing A/B/C) with their steps.

        Agenda-driven: the cover agenda is the authoritative list of sub-blocks
        (section/letter/title/minutes), so it is the skeleton. We then walk the body
        and attach each element's text as steps to the current block, advancing to the
        next block when its title appears. This is robust to Docling labeling a
        sub-block header as a plain ``list_item`` (dropping its letter) — matching on
        title, not label, still finds it and prevents its steps being mis-attributed
        to the previous block.
        """
        agenda = self.agenda()
        blocks = [
            InstructionalBlock(section=a.section, letter=a.letter, title=a.title,
                               minutes=a.minutes, page=0, steps=[])
            for a in agenda
        ]
        if not blocks:
            return []
        return fill_steps(blocks, [
            (el.label, _clean(el.text), el.page)
            for el in self.elements
            if el.label not in ("page_header", "page_footer")
        ], self.cfg)

    def materials(self) -> list[str]:
        return [
            t
            for t in self._collect_under(("Materials",))
            if not tu.is_prep_or_tip_noise(t)
        ]

    def vocabulary(self) -> list[str]:
        # "N/A" is the publisher's placeholder for "no new/review vocabulary this
        # lesson" — a real value, not a term. The PyMuPDF fallback filters it too.
        return self._collect_vocabulary()

    def tables(self) -> list[Table]:
        # Only genuine multi-column tables. 1-column "tables" are bulleted lists
        # Docling mis-detected; their content is captured as materials/vocabulary.
        return [
            Table(
                page=t.page,
                n_rows=t.n_rows,
                n_cols=t.n_cols,
                cells=t.cells,
                provenance=Provenance(source_id=self.source_id, page_start=t.page, page_end=t.page),
            )
            for t in self._raw_tables
            if t.n_cols >= 2
        ]


def divide(docling: DoclingParse, span: LessonSpan, cfg: Config) -> Lesson:
    """Parse a single lesson span into a ``Lesson`` using Docling's structure."""
    d = _DoclingDivider(docling, span, cfg)
    return Lesson(
        code=span.code,
        grade=span.grade,
        module=span.module,
        unit=span.unit,
        lesson=span.lesson,
        title=d.title(),
        page_start=span.page_start,
        page_end=span.page_end,
        declared_standards=d.declared_standards(),
        learning_targets=d.learning_targets(),
        agenda=d.agenda(),
        instructional_blocks=d.instructional_blocks(),
        materials=d.materials(),
        vocabulary=d.vocabulary(),
        tables=d.tables(),
        parsed_by="docling",
        provenance=Provenance(
            source_id=docling.source_id,
            page_start=span.page_start,
            page_end=span.page_end,
        ),
    )
