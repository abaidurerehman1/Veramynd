"""P5: ban invented while-reading vs after-reading timing requirements."""

from __future__ import annotations

import re

# Contrast / gate language that invents a timing bar the standard does not state.
_TIMING_GATE = re.compile(
    r"(?i)("
    r"(?:while|during)\s+reading.{0,100}(?:\bafter\b|not after)|"
    r"after\s+(?:the\s+)?reading.{0,100}(?:while|during|not during)|"
    r"after\s+reading.{0,100}(?:while|during|not during)|"
    r"(?:only|must|required|needs?\s+to|should)\s+(?:occur\s+|happen\s+|be\s+)?"
    r"(?:while|during|after)\s+reading|"
    r"(?:because|since|as)\s+it\s+(?:occurs|happens|is\s+done|takes\s+place)\s+"
    r"(?:only\s+)?after\s+reading|"
    r"(?:not|never)\s+(?:done|practiced|performed)\s+while\s+reading|"
    r"(?:while|during)\s+reading.{0,80}(?:partial|none|not\s+(?:fully\s+)?met|insufficient)|"
    r"(?:partial|none|not\s+(?:fully\s+)?met|insufficient).{0,80}(?:while|during|after)\s+reading"
    r")"
)

_P5_NOTE = (
    "[P5: invented while-reading vs after-reading timing disregarded — "
    "score on the skill only]"
)


def invents_reading_timing_requirement(rationale: str) -> bool:
    """True when the rationale uses while/during vs after reading as a score gate."""
    text = (rationale or "").strip()
    if not text:
        return False
    return bool(_TIMING_GATE.search(text))


def scrub_invented_timing_rationale(rationale: str) -> tuple[str, bool]:
    """Remove timing-gate sentences; append P5 note when any were found.

    Returns (cleaned_rationale, scrubbed).
    """
    text = (rationale or "").strip()
    if not text or not invents_reading_timing_requirement(text):
        return text, False

    kept: list[str] = []
    # Split on sentence boundaries while keeping delimiters loosely.
    parts = re.split(r"(?<=[.!?])\s+", text)
    for part in parts:
        p = part.strip()
        if not p:
            continue
        if _TIMING_GATE.search(p) or (
            re.search(r"(?i)\b(?:while|during|after)\s+reading\b", p)
            and re.search(
                r"(?i)\b(?:partial|none|not\s+(?:fully\s+)?met|only|must|required|because|since)\b",
                p,
            )
        ):
            continue
        kept.append(p)

    cleaned = " ".join(kept).strip()
    if not cleaned:
        cleaned = (
            "Timing while/after reading is not a scoring requirement; "
            "score on whether students perform the target skill."
        )
    if _P5_NOTE not in cleaned:
        cleaned = f"{cleaned} {_P5_NOTE}".strip()
    return cleaned, True


__all__ = [
    "invents_reading_timing_requirement",
    "scrub_invented_timing_rationale",
]
