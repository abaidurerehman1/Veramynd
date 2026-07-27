"""Text normalization and pattern matching.

These helpers encode the small, hard-won rules that make extraction from this
document reliable — the bullet glyph, the soft-hyphen line wraps, the standard-code
grammar. Each one exists because the raw PDF text broke a naive approach.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

# The teacher guide's list bullet is a private-use glyph in the heading font.
BULLET = "\x84"

# Typographic punctuation -> ASCII, so both engines yield byte-identical text
# (Docling normalizes curly quotes to straight; PyMuPDF preserves the originals).
_PUNCT_MAP = str.maketrans({
    "‘": "'", "’": "'",   # ‘ ’ -> '
    "“": '"', "”": '"',   # “ ” -> "
})

# CCSS-style (and close variants) standard codes in teacher-guide prose.
# Backward compatible with RL.1.1 / SL.1.1a / RF.1.2b; also allows:
#   - 1–4 letter prefixes (e.g. CCR.R.1-style short forms still need digit.digit)
#   - kindergarten "K" grade segment (RL.K.1)
#   - longer letter suffixes (L.1.1fg) while keeping single-letter forms
STANDARD_CODE = re.compile(
    r"\b([A-Z]{1,4}\.(?:K|\d+)\.\d+[a-z]{0,3})\b"
)

# The teacher-guide lesson code embedded in bookmarks and page text.
LESSON_CODE = re.compile(r"^G(\d+)M(\d+)U(\d+)L(\d+)")

# Running header on lesson pages. Full form captures Grade/Module when present;
# Unit/Lesson groups stay at the end for verifier V7 compatibility.
# e.g. "Grade 1: Module 2: Unit 1: Lesson 1" or just "Unit 1: Lesson 1".
RUNNING_HEADER = re.compile(
    r"(?:Grade\s+(\d+)\s*:\s*)?(?:Module\s+(\d+)\s*:\s*)?Unit\s+(\d+)\s*:\s*Lesson\s+(\d+)",
    re.IGNORECASE,
)

# A bare footer page number, e.g. "66" on its own line.
_BARE_PAGE_NUMBER = re.compile(r"^\d{1,4}$")
# The footer signature, e.g. "EL Education Curriculum 117".
_CURRICULUM_FOOTER = re.compile(r"Curriculum\s+\d{1,4}\s*$", re.I)

# An agenda timing token: "(10 minutes)".
MINUTES = re.compile(r"\((\d+)\s*minutes?\)")

# Agenda structure lines.
AGENDA_SECTION = re.compile(r"^\d+\.\s*(.+)")          # "1. Opening"
AGENDA_ITEM = re.compile(r"^([A-Z])\.\s*(.+)")         # "A. Reading Aloud ... (10 minutes)"

# A standard code that word-wrapped without a hyphen right before its final
# numeric segment, e.g. 'RL.1.\n1' -> 'RL.1.1'. Prefix/grade segments mirror
# STANDARD_CODE (1-4 letter prefix, K or digits for grade) so a code that would
# otherwise be recognized post-stitch is never missed just because it wrapped.
_WRAPPED_STANDARD_CODE = re.compile(r"\b([A-Z]{1,4}\.(?:K|\d+)\.)\s*\n\s*(\d+[a-z]?)\b")

# A safe filename component: no path separators, no traversal, non-empty.
_SAFE_CODE = re.compile(r"^[A-Za-z0-9_-]+$")


def dehyphenate(text: str) -> str:
    """Stitch soft-hyphen line wraps: 'min-\\nutes' -> 'minutes'.

    The PDF wraps words at line ends with a hyphen ('min-' / 'utes'). Left as-is,
    this splits '(5 minutes)' so the timing regex misses it and a lesson's agenda
    under-counts. This is the fix the safety-net verifier's timing check surfaced.
    """
    return re.sub(r"-\s*\n\s*", "", text)


def stitch_wrapped_minutes(text: str) -> str:
    """Join a duration token that word-wrapped without a hyphen.

    Two wrap styles occur in the agenda: hyphenated ('(5 min-\\nutes)', handled by
    :func:`dehyphenate`) and plain ('(20\\nminutes)', where the number ends a line
    and 'minutes)' starts the next). This joins the plain case so a line-by-line
    parser keeps the duration attached to its agenda item.
    """
    return re.sub(r"\((\d+)\s*\n\s*(minutes?\))", r"(\1 \2", text)


def clean_line(text: str) -> str:
    """Normalize a single extracted line: drop bullets/tabs, collapse whitespace.

    Also removes a space before closing punctuation ('Sky .' -> 'Sky.'), which the
    layout engine can introduce around italic runs — so the two engines produce
    identical text for the same content.
    """
    out = re.sub(r"\s+", " ", text.replace(BULLET, " ").replace("\t", " ")).strip()
    out = out.translate(_PUNCT_MAP)
    return re.sub(r"\s+([.,;:!?)])", r"\1", out)


def stitch_wrapped_standard_code(text: str) -> str:
    """Join a standard code that word-wrapped without a hyphen mid-code.

    Mirrors :func:`stitch_wrapped_minutes` for the analogous wrap in a standard
    code (e.g. 'RL.1.\\n1' -> 'RL.1.1'). Left as-is, a bare ``\\s+`` -> ' '
    collapse turns this into 'RL.1. 1', which breaks the exact-substring
    grounding check (verifier V10) even though the code is genuinely present.
    """
    return _WRAPPED_STANDARD_CODE.sub(r"\1\2", text)


def normalize_block(text: str) -> str:
    """Normalize a multi-line block of text for pattern matching.

    De-hyphenate and re-stitch wrapped standard codes first (so wrapped tokens
    rejoin), then strip bullets and collapse runs of whitespace — but keep it as
    a single searchable string.
    """
    stitched = stitch_wrapped_standard_code(dehyphenate(text))
    return re.sub(r"\s+", " ", stitched.replace(BULLET, " ")).strip()


def atomic_write_text(path: str | Path, text: str, encoding: str = "utf-8") -> None:
    """Write text via temp-file-then-rename, so a crash or concurrent reader can
    never observe a truncated/partial file at the real path.

    Temp siblings are always removed on failure (``try``/``finally``).
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(f"{path.suffix}.{os.getpid()}.tmp")
    try:
        tmp.write_text(text, encoding=encoding)
        tmp.replace(path)
        tmp = None  # type: ignore[assignment]
    finally:
        if tmp is not None and tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass


def atomic_replace_dir(src: Path | str, dest: Path | str) -> None:
    """Replace ``dest`` directory with a copy of ``src`` via rename-swap.

    Never deletes ``dest`` before the replacement is ready. On failure, rolls
    back so either the previous ``dest`` is restored or the new tree is left
    intact — callers never see an empty half-promoted lessons folder.
    """
    import shutil

    src = Path(src)
    dest = Path(dest)
    if not src.is_dir():
        raise NotADirectoryError(f"atomic_replace_dir source is not a directory: {src}")

    parent = dest.parent
    parent.mkdir(parents=True, exist_ok=True)
    staging = parent / f".{dest.name}.__new__.{os.getpid()}"
    backup = parent / f".{dest.name}.__old__.{os.getpid()}"

    for path in (staging, backup):
        if path.exists():
            shutil.rmtree(path)

    shutil.copytree(src, staging)
    try:
        if dest.exists():
            dest.rename(backup)
        staging.rename(dest)
    except OSError:
        if not dest.exists() and backup.exists():
            try:
                backup.rename(dest)
            except OSError:
                pass
        if staging.exists():
            shutil.rmtree(staging, ignore_errors=True)
        raise
    else:
        if backup.exists():
            shutil.rmtree(backup, ignore_errors=True)

def safe_code_filename(code: str) -> str:
    """Validate a lesson/standard code is safe to use as an output filename.

    Codes are used verbatim as ``{code}.json`` output filenames in several
    places. An empty, path-separator-containing, or otherwise malformed code
    would silently collide with another file or escape the output directory —
    this raises instead of allowing that.
    """
    if not code or not _SAFE_CODE.match(code):
        raise ValueError(f"unsafe code for use as a filename: {code!r}")
    return code


def dedupe_preserve_order(items: list[str]) -> list[str]:
    """De-duplicate while keeping first-seen order.

    Used wherever codes are collected from document text: the publisher's own
    ordering (e.g. CCS Standards usually lists the "headline" standard first) is
    meaningful and lost by an alphabetical ``sorted(set(...))`` -- the codes are
    the same set either way, but which one a reader sees first is not.
    """
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            out.append(item)
    return out


def extract_standard_codes(text: str) -> list[str]:
    """All standard codes in a string, de-duplicated, in first-seen order."""
    return dedupe_preserve_order(STANDARD_CODE.findall(text))


def parse_lesson_code(title: str) -> tuple[int, int, int, int] | None:
    """Parse 'G1M2U1L1...' -> (grade, module, unit, lesson), or None if not a lesson."""
    m = LESSON_CODE.match(title)
    if not m:
        return None
    return tuple(int(g) for g in m.groups())  # type: ignore[return-value]


def strip_trailing_codes(text: str) -> str:
    """Remove a trailing '(RL.1.1, ...)' code tail from a learning-target line."""
    return re.split(r"\s*\(?[A-Z]{1,3}\.\d", text)[0].strip()


def is_page_furniture(text: str) -> bool:
    """True if a cleaned line is running-header/footer noise, not real content.

    A tier-based section-body collector (see pdf/divider.py) assumes page
    furniture always classifies as a recognizable section header (tier 2), so it
    is naturally excluded. That assumption breaks for furniture that happens to
    render at body/run-in size instead — a bare footer page number, the running
    header, or the 'EL Education Curriculum N' footer signature — which then gets
    swept into whatever section is collecting across the page break.
    """
    return bool(
        _BARE_PAGE_NUMBER.match(text)
        or RUNNING_HEADER.search(text)
        or _CURRICULUM_FOOTER.search(text)
    )


# Teaching-notes prep / logistics that must not land in materials or vocabulary.
_PREP_OR_TIP = re.compile(
    r"^\s*[-–—•]?\s*(?:"
    r"Post\s*:"
    r"|In advance\b"
    r"|During (?:Opening|Work Time|Closing)\b"
    r"|Circulate\b"
    r"|Prepare\b"
    r"|Refer to the Classroom Protocols\b"
    r")",
    re.I,
)
_ROUTINE_PROTOCOL_PREP = re.compile(
    r"^\s*[-–—•]\s*.*\b(?:routine|protocols?)\b",
    re.I,
)


def is_prep_or_tip_noise(text: str) -> bool:
    """True for Teaching Notes prep bullets / circulate tips, not list content.

    Materials and Vocabulary sections that span a page break (or that Docling
    mis-orders) sometimes absorb 'In advance' prep bullets and teacher-circulate
    tips. Those are not materials or vocabulary terms.
    """
    t = (text or "").strip()
    if not t:
        return True
    if _PREP_OR_TIP.match(t):
        return True
    if _ROUTINE_PROTOCOL_PREP.match(t):
        return True
    return False


# canonical instructional-section names, matched leniently by prefix
_AGENDA_SECTIONS = (("Opening", "Opening"), ("Work Time", "Work Time"),
                    ("Closing", "Closing and Assessment"))


def norm_key(s: str) -> str:
    """Lowercased alphanumeric-only key, for lenient title matching across engines."""
    return re.sub(r"[^a-z0-9]", "", s.lower())


def canonical_agenda_section(name: str) -> str | None:
    """Map an agenda section label to its canonical name, or None if it isn't one.

    Handles publisher variation — the agenda sometimes abbreviates
    'Closing and Assessment' to just 'Closing'. Matching by prefix keeps both forms
    (and any future 'Opening A'-style suffixing) mapping to the same section.
    """
    for prefix, canonical in _AGENDA_SECTIONS:
        if name.startswith(prefix):
            return canonical
    return None
