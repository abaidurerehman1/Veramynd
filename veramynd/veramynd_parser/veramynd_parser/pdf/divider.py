"""Lesson division — split one lesson into its structured parts.

Given a lesson's page span, recover its internal structure from the font hierarchy
and the document's own conventions:

  * title              — the tier-1 heading(s) on the cover
  * declared_standards — codes under the 'CCS Standards' section (the CLAIM)
  * learning_targets   — 'I can ...' lines, each with its tagged standard codes
  * agenda             — timed sub-blocks (with soft-hyphen wrapping handled)
  * body_sections      — the Opening / Work Time / Closing majors, with pages

The Agenda is read from the raw text of the first few pages (it can spill past the
cover when the standards list is long), and de-hyphenated first so wrapped
'(5 min-utes)' tokens are counted.
"""

from __future__ import annotations

import re

from .. import text_utils as tu
from ..config import Config
from ..fonts import TIER_BODY, TIER_MAJOR, TIER_RUNIN, TIER_SECTION, classify
from ..models import AgendaItem, InstructionalBlock, LearningTarget, Lesson, Provenance
from .division import fill_steps
from .document import Line, PdfDocument
from .separator import LessonSpan

# A body/title line ending in a soft-hyphen word-wrap ("Ques-", "sup-").
# clean_line() has already collapsed each Line's own internal whitespace by
# the time callers see this text, so the join must happen where two adjacent
# Line objects meet — dehyphenate() only fires on an actual "-\n" boundary,
# which only exists here, before it gets flattened to "-  " by a plain join.
_HYPHEN_WRAP = re.compile(r"\w-$")


class _Divider:
    """Holds the per-lesson parsing state. One instance per lesson."""

    def __init__(self, doc: PdfDocument, span: LessonSpan, cfg: Config):
        self.doc = doc
        self.span = span
        self.cfg = cfg
        self.lines: list[Line] = doc.lines(span.page_start, span.page_end)
        # tier of each line's head span, computed once
        self.tiers: list[int] = [classify(ln.head, cfg.fonts) for ln in self.lines]

    # -- helpers ---------------------------------------------------------- #
    def _is_section(self, text: str) -> bool:
        clean = tu.clean_line(text)
        return any(clean.startswith(h) for h in self.cfg.section_headers)

    # -- fields ----------------------------------------------------------- #
    def title(self) -> str:
        """Concatenate the tier-1 title lines on the cover, before the first section."""
        parts: list[str] = []
        started = False
        for line, tier in zip(self.lines, self.tiers):
            text = tu.clean_line(line.text)
            if tier == TIER_MAJOR and "Lesson" in text and not text.startswith("Grade"):
                parts.append(text)
                started = True
            elif started and tier == TIER_MAJOR and text not in self.cfg.instructional_sections:
                parts.append(text)
            elif started:
                break
        # dehyphenate() needs a real newline to find the wrap point — join with
        # "\n" first, then collapse whatever it leaves behind to a single space.
        return tu.dehyphenate("\n".join(parts)).replace("\n", " ")

    def declared_standards(self) -> list[str]:
        """Standard codes listed under the 'CCS Standards' section (the publisher's claim).

        Kept in the order the guide lists them, not alphabetized — the publisher's
        own ordering is meaningful (see text_utils.dedupe_preserve_order).
        """
        codes: list[str] = []
        collecting = False
        for line, tier in zip(self.lines, self.tiers):
            text = tu.clean_line(line.text)
            if tier == TIER_SECTION and text == "CCS Standards":
                collecting = True
                continue
            if collecting:
                if tier == TIER_MAJOR or (tier == TIER_SECTION and self._is_section(text)):
                    break
                codes.extend(tu.STANDARD_CODE.findall(text))
        return tu.dedupe_preserve_order(codes)

    def learning_targets(self) -> list[LearningTarget]:
        """'I can ...' statements under 'Daily Learning Target(s)', with tagged codes.

        Read from raw text (de-hyphenated) across the cover pages, because a target
        and its trailing code list often span a line break.
        """
        raw = tu.dehyphenate(self._cover_text())
        idx = raw.find("Daily Learning Target")
        if idx < 0:
            return []
        segment = raw[idx:]
        # stop at the next section
        for stop in ("Ongoing Assessment", "Agenda"):
            j = segment.find(stop)
            if j > 0:
                segment = segment[:j]
                break
        targets: list[LearningTarget] = []
        for chunk in segment.split(tu.BULLET):
            text = tu.clean_line(chunk)
            if text.startswith("I can"):
                codes = tu.extract_standard_codes(text)
                targets.append(
                    LearningTarget(text=tu.strip_trailing_codes(text), codes=codes)
                )
        return targets

    def agenda(self) -> list[AgendaItem]:
        """Timed sub-blocks from the Agenda. Handles both line-wrap styles.

        Durations wrap two ways in this document — hyphenated ('(5 min-utes)') and
        plain ('(20 minutes)' broken after the number). Both are stitched before the
        line-by-line parse so no duration is lost.
        """
        raw = tu.stitch_wrapped_minutes(tu.dehyphenate(self._cover_text()))
        idx = raw.find("Agenda")
        if idx < 0:
            return []
        segment = raw[idx + len("Agenda"):]
        # the Agenda ends where Teaching Notes begins
        stop = segment.find("Teaching Notes")
        if stop > 0:
            segment = segment[:stop]

        items: list[AgendaItem] = []
        section: str | None = None
        for raw_line in segment.split("\n"):
            line = raw_line.replace("\t", " ").strip()
            if not line:
                continue
            sec = tu.AGENDA_SECTION.match(line)
            canon = tu.canonical_agenda_section(sec.group(1).strip()) if sec else None
            if canon:
                section = canon
                continue
            item = tu.AGENDA_ITEM.match(line)
            mins = tu.MINUTES.search(line)
            if item and section:
                title = tu.MINUTES.sub("", item.group(2)).strip()
                items.append(
                    AgendaItem(
                        section=section,
                        letter=item.group(1),
                        title=title,
                        minutes=int(mins.group(1)) if mins else None,
                    )
                )
            elif mins and items and items[-1].minutes is None:
                # a duration that wrapped onto its own line — attach to the last item
                items[-1].minutes = int(mins.group(1))
        return items

    def instructional_blocks(self) -> list[InstructionalBlock]:
        """Body sub-blocks with steps — agenda-driven (see :mod:`.division`).

        The agenda is the authoritative sub-block list; body tier-0 lines become the
        steps, tier-1 majors mark the body start, and a tier-3 header matching the
        next block's title advances to it.
        """
        agenda = self.agenda()
        blocks = [
            InstructionalBlock(section=a.section, letter=a.letter, title=a.title,
                               minutes=a.minutes, page=0, steps=[])
            for a in agenda
        ]
        if not blocks:
            return []
        body: list[tuple[str, str, int]] = []
        for line, tier in zip(self.lines, self.tiers):
            text = tu.clean_line(line.text)
            if not text:
                continue
            if tier == TIER_MAJOR and text in self.cfg.instructional_sections:
                body.append(("section_header", text, line.page))
            elif tier == TIER_RUNIN and tu.AGENDA_ITEM.match(text):
                body.append(("section_header", text, line.page))  # a sub-block header
            elif tier == TIER_BODY:
                # A mid-word line wrap must not become two separate steps (or
                # leave "sup-" / "porting" straddling fill_steps' key match) —
                # merge into the previous list_item instead.
                if body and body[-1][0] == "list_item" and _HYPHEN_WRAP.search(body[-1][1]):
                    prev_label, prev_text, prev_page = body[-1]
                    merged = tu.dehyphenate(f"{prev_text}\n{text}").replace("\n", " ")
                    body[-1] = (prev_label, merged, prev_page)
                else:
                    body.append(("list_item", text, line.page))
        return fill_steps(blocks, body, self.cfg)

    def _section_body(self, header: str) -> list[str]:
        """Body/run-in lines under a tier-2 section header, until the next section.

        Running headers (tier-2 but not a known section) neither stop collection nor
        are collected, so a section that spans pages is captured whole. Page
        furniture that renders at body/run-in size instead of tier-2 — a bare
        footer page number, the running header, the 'EL Education Curriculum N'
        footer signature — is filtered the same way. A collected line that never
        closes an opened parenthesis is a PDF line-wrap of the next line, not a
        separate item, so it merges into it rather than becoming its own entry.
        """
        out: list[str] = []
        collecting = False
        for line, tier in zip(self.lines, self.tiers):
            text = tu.clean_line(line.text)
            if tier == TIER_SECTION and text == header:
                collecting = True
                continue
            if collecting:
                is_stop = (tier == TIER_MAJOR and text in self.cfg.instructional_sections) or (
                    tier == TIER_SECTION and self._is_section(text) and text != header
                )
                if is_stop:
                    break
                if tier in (TIER_BODY, TIER_RUNIN) and text and not tu.is_page_furniture(text):
                    if out and _HYPHEN_WRAP.search(out[-1]):
                        # Mid-word line wrap: join without the space the
                        # open-paren rule below would insert.
                        out[-1] = tu.dehyphenate(f"{out[-1]}\n{text}").replace("\n", " ")
                    elif out and out[-1].count("(") > out[-1].count(")"):
                        # Not a hyphen wrap, so dehyphenate() leaves the "\n" I
                        # inserted untouched — still need the plain-space join.
                        out[-1] = tu.dehyphenate(f"{out[-1]}\n{text}").replace("\n", " ")
                    else:
                        out.append(text)
        return out

    def materials(self) -> list[str]:
        return [
            t
            for t in self._section_body("Materials")
            if t not in ("Materials",) and not tu.is_prep_or_tip_noise(t)
        ]

    def vocabulary(self) -> list[str]:
        """Preserve New vs Review; skip legend, furniture, and In-advance prep."""
        legend = ("(L):", "(T):", "(W):")
        out: list[str] = []
        section: str | None = None
        for t in self._section_body("Vocabulary"):
            if t == "N/A" or t.startswith(legend) or t == "Key:":
                continue
            if t == "New:" or t.startswith("New:"):
                section = "new"
                rest = t[len("New:") :].strip() if t.startswith("New:") else ""
                if rest and not tu.is_page_furniture(rest) and not tu.is_prep_or_tip_noise(rest):
                    out.append(rest)
                continue
            if t == "Review:" or t.startswith("Review:"):
                section = "review"
                rest = t[len("Review:") :].strip() if t.startswith("Review:") else ""
                if rest and not tu.is_page_furniture(rest) and not tu.is_prep_or_tip_noise(rest):
                    out.append(f"Review: {rest}")
                continue
            if tu.is_page_furniture(t) or tu.is_prep_or_tip_noise(t):
                continue
            if section == "review":
                out.append(f"Review: {t}" if not t.lower().startswith("review:") else t)
            else:
                out.append(t)
        return out

    # -- internals -------------------------------------------------------- #
    def _cover_text(self) -> str:
        last = min(self.span.page_end, self.span.page_start + self.cfg.cover_scan_pages - 1)
        return self.doc.text_range(self.span.page_start, last)


def divide(doc: PdfDocument, span: LessonSpan, cfg: Config) -> Lesson:
    """Parse a single lesson span into a fully populated ``Lesson``."""
    d = _Divider(doc, span, cfg)
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
        parsed_by="pymupdf",
        provenance=Provenance(
            source_id=doc.source_id,
            page_start=span.page_start,
            page_end=span.page_end,
        ),
    )
