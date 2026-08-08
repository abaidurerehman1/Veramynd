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
from ..models import AgendaItem, InstructionalBlock, LearningTarget


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

    Fuzzy matching is gated on ``label == "section_header"`` because it is a partial
    signal (a shared prefix, not full equality) and ordinary body prose can trigger it
    by coincidence: a real lesson had a body sentence "...use the shared writing."
    whose normalized key ("sharedwriting") is a complete prefix of a later block's key
    ("sharedwritingdescribingthepositionofthesun") -- 13 shared characters, past
    MIN_PREFIX. That false match advanced `idx` past an intervening block (which then
    never matched at all -- caught by V13) and, worse, silently absorbed the rest of
    that intervening block's steps plus the real target block's steps into the wrong
    block (NOT caught by any verifier check, since every block still ended up with
    >=1 step). Exact matches stay label-agnostic because full key equality on
    ordinary prose is not a realistic coincidence.
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
    for label, text, page in body:
        if label == "section_header" and text in cfg.instructional_sections:
            in_body = True
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
            elif label == "section_header" and shared >= MIN_PREFIX:
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
            blocks[idx].steps.append(text)
    return blocks
