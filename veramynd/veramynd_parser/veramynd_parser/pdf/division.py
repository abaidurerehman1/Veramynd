"""Shared contract and matching logic between the two lesson dividers.

Docling (docling_divider.py) and PyMuPDF (divider.py) each recover a lesson's
structure by a different route — semantic labels vs. font tiers — but they must
expose the same shape and share the one piece of logic that is genuinely
engine-agnostic: attaching body step-text to an agenda-derived block skeleton.
Neither engine module should own this — that made the "fallback" engine depend
on the "primary" one's module for something that isn't Docling-specific at all.
"""

from __future__ import annotations

import re
from typing import Protocol

from .. import text_utils as tu
from ..models import AgendaItem, InstructionalBlock, InstructionalStep, LearningTarget


class LessonDivider(Protocol):
    """Structural contract both per-engine dividers satisfy.

    Not enforced by inheritance (each engine's divider is built from a different
    source view — Docling elements vs. font-classified lines — so a shared base
    class would just be an empty formality). Enforced instead by a test that
    checks both concrete classes actually expose this surface.
    """

    def title(self) -> str: ...
    def declared_standards(self) -> list[str]: ...
    def learning_targets(self) -> list[LearningTarget]: ...
    def agenda(self) -> list[AgendaItem]: ...
    def instructional_blocks(self) -> list[InstructionalBlock]: ...
    def materials(self) -> list[str]: ...
    def vocabulary(self) -> list[str]: ...


def _instructional_major_name(text: str, cfg) -> str | None:
    """Return canonical instructional major for a header, or None.

    Docling often prints numbered majors (``1. Opening``, ``2. Work Time``).
    Agenda parsing already tolerates that form; ``fill_steps`` must too, or the
    body never opens and Opening/A stays at page 0 (V13 BLOCK).
    """
    raw = (text or "").strip()
    if not raw:
        return None
    majors = tuple(cfg.instructional_sections)
    if raw in majors:
        return raw
    stripped = re.sub(r"^\d+\.\s*", "", raw).strip()
    if stripped in majors:
        return stripped
    canon = tu.canonical_agenda_section(stripped)
    if canon in majors:
        return canon
    return None


def _is_cover_boundary(text: str, cfg) -> bool:
    """True for cover/body boundary headers that sit after the agenda."""
    raw = (text or "").strip()
    if not raw:
        return False
    if raw.startswith("Daily Learning Target"):
        return True
    # section_headers includes Materials, Vocabulary, CCS Standards, etc.
    # Exclude Agenda itself — that opens the cover agenda, not the body.
    boundaries = (set(getattr(cfg, "section_headers", ()) or ()) | {"Teaching Notes"}) - {
        "Agenda"
    }
    if raw in boundaries:
        return True
    return any(raw.startswith(h) for h in boundaries if h)


def _looks_like_block_header(text: str) -> bool:
    """True for lettered / timed activity titles Docling often labels ``list_item``.

    Ordinary body prose must stay out of fuzzy matching (see fill_steps docstring).
    EL body sub-block headers almost always carry ``(N minutes)`` and/or an
    ``A.`` / ``B.`` letter prefix — use those as the gate, not the Docling label.
    """
    raw = (text or "").strip()
    if not raw:
        return False
    if tu.MINUTES.search(raw):
        return True
    return bool(re.match(r"^[A-Za-z]\.\s+\S", raw))


def fill_steps(blocks: list[InstructionalBlock], body, cfg) -> list[InstructionalBlock]:
    """Attach body step-text to an agenda-derived block skeleton.

    ``blocks`` is the ordered list of InstructionalBlock skeletons (from the agenda);
    ``body`` is a list of ``(label, text, page)`` tuples in reading order. We start
    collecting once the body reaches the first instructional major, then advance to
    the next block whenever an element matches that block's title. An *exact* key
    match is label-agnostic (so a header either engine mislabeled as a plain item is
    still found); a *fuzzy* (shared-prefix) match is restricted to candidates already
    labeled ``section_header`` -- see the false-positive note below.

    The match window looks ahead a bounded number of blocks (not just the very next
    one): if the engine ever fails to surface one sub-block's header text distinctly
    (a Docling labeling quirk, a font-classification miss), a single missed match
    used to cascade -- every subsequent step kept attaching to the last successfully
    matched block instead of the one it actually belongs to, silently, since V13 only
    catches a block matched *zero* times. Looking a few blocks ahead lets the scan
    resynchronize on the next block whose title *does* appear, at the cost of the
    skipped block's own `page` staying 0 (still correctly flagged by V13) rather than
    corrupting every block after it too.

    Fuzzy matching is gated on ``section_header`` *or* a line that looks like a
    lettered/timed block header (``A. …`` / ``(N minutes)``). Docling often emits
    body sub-block titles as ``list_item`` (seen on G1M2U1L9 Opening/A, where the
    body also adds "Version 2" so exact match fails). Ordinary body prose must stay
    out of fuzzy matching: a real lesson had "...use the shared writing." whose
    normalized key ("sharedwriting") is a complete prefix of a later block's key
    ("sharedwritingdescribingthepositionofthesun") -- 13 shared characters, past
    MIN_PREFIX. That false match advanced `idx` past an intervening block (which then
    never matched at all -- caught by V13) and, worse, silently absorbed the rest of
    that intervening block's steps plus the real target block's steps into the wrong
    block (NOT caught by any verifier check, since every block still ended up with
    >=1 step). Exact matches stay label-agnostic because full key equality on
    ordinary prose is not a realistic coincidence.

    Body start is delayed until after the cover agenda: the first ``1. Opening`` /
    ``Opening`` after ``Agenda`` is still the cover section label. We open the body
    only after a cover boundary (Materials / Teaching Notes / …) or when the same
    major appears a second time (body repeat). Streams with no ``Agenda`` marker
    (PyMuPDF path) still open on the first major.
    """
    LOOKAHEAD = 3
    # Minimum shared alphanumeric prefix to treat a body line as a block header.
    # Long enough to avoid weak collisions; short enough for truncated body headers.
    MIN_PREFIX = 12

    def key(s: str) -> str:
        # strip a leading letter/number prefix and any duration, then normalize
        s = re.sub(r"^[A-Za-z0-9]\.\s*", "", tu.MINUTES.sub("", s)).strip()
        return tu.norm_key(s)

    def shared_prefix_len(a: str, b: str) -> int:
        n = 0
        for x, y in zip(a, b):
            if x != y:
                break
            n += 1
        return n

    # Full keys — never truncate to a fixed width (that collided on titles like
    # "Unit 2 Assessment, Group 1/2"). Match by longest shared prefix so a
    # slightly truncated body header still finds its agenda block, while Group 1
    # vs Group 2 still disambiguate on the longer distinct prefix.
    block_keys = [key(b.title) for b in blocks]
    idx = -1
    in_body = False
    seen_agenda = False
    past_cover = False
    seen_majors: set[str] = set()
    for label, text, page in body:
        if label == "section_header":
            if text == "Agenda" or text.startswith("Agenda"):
                seen_agenda = True
                past_cover = False
                continue
            if _is_cover_boundary(text, cfg):
                past_cover = True
                continue
            major = _instructional_major_name(text, cfg)
            if major:
                # Open body on: no Agenda in stream | after cover boundary |
                # second sighting of this major (cover then body).
                if (not seen_agenda) or past_cover or major in seen_majors:
                    in_body = True
                    continue
                seen_majors.add(major)
                continue
        if not in_body:
            continue
        matched = False
        text_key = key(text)
        best: tuple[int, int, int] | None = None  # (rank, -shared, nxt)
        for lookahead in range(1, LOOKAHEAD + 1):
            nxt = idx + lookahead
            if nxt >= len(blocks):
                break
            if not block_keys[nxt]:
                # An empty agenda title can't be matched, but blocks past it
                # still can — breaking here disabled resync for the rest of
                # the lesson (the exact cascade LOOKAHEAD exists to prevent).
                continue
            bk = block_keys[nxt]
            shared = shared_prefix_len(text_key, bk)
            if text_key == bk:
                score = (0, -shared, nxt)
            elif (
                (label == "section_header" or _looks_like_block_header(text))
                and shared >= MIN_PREFIX
            ):
                score = (1, -shared, nxt)
            else:
                continue
            if best is None or score < best:
                best = score
        if best is not None:
            idx = best[2]
            blocks[idx].page = page
            matched = True
        if matched:
            continue
        if idx >= 0 and label in ("list_item", "text"):
            blocks[idx].steps.append(InstructionalStep(text=text, page=page))
    return blocks
