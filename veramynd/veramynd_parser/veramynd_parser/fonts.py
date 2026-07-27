"""Font-tier classification — the mechanism behind lesson division.

The teacher guide has no logical structure tree (it is an untagged PDF), so we
recover structure from typography. Three tiers, each mapping to a structural role:

    tier 1  (>= 12.5pt, MarkPro)          -> MAJOR block  (title, Opening, Work Time)
    tier 2  (10.4-11.6pt)                 -> SECTION       (CCS Standards, Agenda, ...)
    tier 3  (9.0-9.9pt, bold, NOT italic) -> RUN-IN label  (Purpose:, Key:, ...)
    tier 0  (everything else)             -> body text

The bold-vs-bold-italic distinction in tier 3 matters: a 9.5pt bold run is a real
label, but a 9.5pt bold-*italic* run is a scripted classroom utterance (sample
teacher/student dialogue), not a heading.
"""

from __future__ import annotations

from dataclasses import dataclass

from .config import FontThresholds

# Tier constants
TIER_MAJOR = 1
TIER_SECTION = 2
TIER_RUNIN = 3
TIER_BODY = 0

_BOLD_HINTS = ("Bold", "Heavy", "Semibold")


@dataclass(frozen=True)
class Span:
    """The minimum a classifier needs about a text span."""

    text: str
    font: str
    size: float
    flags: int = 0

    @property
    def is_bold(self) -> bool:
        return any(h in self.font for h in _BOLD_HINTS)

    @property
    def is_italic(self) -> bool:
        return "Italic" in self.font


def classify(span: Span, thresholds: FontThresholds) -> int:
    """Return the structural tier (0-3) of a span given the font thresholds."""
    size = span.size
    if size >= thresholds.major_min_size and thresholds.major_font_hint in span.font:
        return TIER_MAJOR
    if thresholds.section_min_size <= size <= thresholds.section_max_size:
        return TIER_SECTION
    if (
        thresholds.runin_min_size <= size <= thresholds.runin_max_size
        and span.is_bold
        and not span.is_italic
    ):
        return TIER_RUNIN
    return TIER_BODY
