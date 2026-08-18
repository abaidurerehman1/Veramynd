"""P4 input-scope caveat: supporting read-aloud guides not in the judged text.

This is a disclosure, not a rescore. Labels never change. When a lesson cites a
close/focused read-aloud guide as a separate teacher-reference document and that
guide's question body is not in the judged text, flag the comprehension-family
codes the SME named as likely understated.
"""

from __future__ import annotations

import re

# SME P4 family — GA Grade 1 overlay codes, not a publisher if-tree.
AFFECTED_COMPREHENSION_CODES = frozenset(
    {
        "1.T.RA.2.a",
        "1.T.T.1.a",
        "1.T.T.1.b",
        "1.T.T.1.c",
        "1.P.EICC.3.d",
        "1.P.EICC.3.e",
        "1.P.EICC.3.f",
        "1.P.CP.2.d",
        "1.T.C.2.a",
    }
)

INPUT_SCOPE_CAVEAT = (
    "scored on provided lesson text; likely understated pending the "
    "Read-aloud Guides."
)

# "Close Read-aloud Guide", "Close Readaloud Guide", "Focused Read-aloud Guide"
_GUIDE_CITE = re.compile(
    r"(?i)\b(?:close|focused)[\s-]*read[\s-]*aloud\s+guide\b"
)

# A titled guide section whose body is actually present (not a pointer).
_GUIDE_SECTION_HEADER = re.compile(
    r"(?i)^\s*(?:\[.*?\])?\s*(?:close|focused)[\s-]*read[\s-]*aloud\s+guide\b"
)
_TDQ_LINE = re.compile(
    r"(?i)^\s*(?:[-*]\s*)?(?:ask(?:\s+students)?\s*[:.]|\u201c?[\"']?(?:what|why|how|who|where)\b)"
)
_POINTER_ONLY = re.compile(
    r"(?i)\busing the\b.{0,80}\b(?:close|focused)[\s-]*read[\s-]*aloud\s+guide\b"
    r"|\b(?:close|focused)[\s-]*read[\s-]*aloud\s+guide\b.{0,80}\bfor teacher reference\b"
    r"|\bsee (?:the )?(?:close|focused)[\s-]*read[\s-]*aloud\s+guide\b"
)


def cites_readaloud_guide(lesson_text: str) -> bool:
    """True when the judged text names a close/focused read-aloud guide."""
    return bool(_GUIDE_CITE.search(lesson_text or ""))


def readaloud_guide_body_present(lesson_text: str) -> bool:
    """True when the guide itself (not a pointer) is in the judged text.

    Pointer-only lessons say 'using the Close Read-aloud Guide … (for teacher
    reference)' and never include the text-dependent questions. After the
    client shares the guides, those questions land as a titled section with
    multiple Ask/What/Why lines — that is when this returns True and the
    caveat must not fire.
    """
    text = lesson_text or ""
    if not _GUIDE_CITE.search(text):
        return False
    tdq = 0
    in_guide_section = False
    for line in text.splitlines():
        if _GUIDE_SECTION_HEADER.search(line) and not _POINTER_ONLY.search(line):
            in_guide_section = True
            continue
        if in_guide_section and line.startswith("[") and "]" in line[:40]:
            in_guide_section = False
        if in_guide_section and _TDQ_LINE.search(line):
            tdq += 1
            if tdq >= 3:
                return True
    return False


def missing_readaloud_guide(lesson_text: str) -> bool:
    """Lesson cites a supporting read-aloud guide that is not in the input."""
    if not cites_readaloud_guide(lesson_text):
        return False
    return not readaloud_guide_body_present(lesson_text)


def input_scope_caveat(standard_code: str, lesson_text: str) -> str:
    """Caveat string for one verdict, or empty. Never a label."""
    code = (standard_code or "").strip()
    if code not in AFFECTED_COMPREHENSION_CODES:
        return ""
    if not missing_readaloud_guide(lesson_text):
        return ""
    return INPUT_SCOPE_CAVEAT
