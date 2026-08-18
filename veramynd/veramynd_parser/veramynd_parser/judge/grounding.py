"""Evidence grounding check — reject fabricated judge quotes (zero LLM cost)."""

from __future__ import annotations

import re
import unicodedata


_WS_RE = re.compile(r"\s+")
_ELLIPSIS_RE = re.compile(r"(\.\.\.|…)")
_TRANS = str.maketrans(
    {
        "\u2018": "'",
        "\u2019": "'",
        "\u201c": '"',
        "\u201d": '"',
        "\u2013": "-",
        "\u2014": "-",
        "\u00a0": " ",
    }
)

# Positive claims need a real quote of usable length.
_MIN_EVIDENCE_CHARS = 24
_PAGE_HEADER_RE = re.compile(r"(?i)\(\s*page\s+(\d+)\s*\)")
_STITCH_RE = re.compile(r"\s+/\s+")


def normalize_for_grounding(text: str) -> str:
    """Lowercase, unify quotes/dashes, collapse whitespace and bullet prefixes."""
    s = unicodedata.normalize("NFKC", text or "")
    s = s.translate(_TRANS)
    s = s.lower()
    s = re.sub(r"(?m)^\s*-\s*", " ", s)
    s = _WS_RE.sub(" ", s).strip()
    return s


def _segment_evidence(needle: str) -> list[str]:
    """Split stitched quotes on ellipsis; drop empty pieces."""
    parts = _ELLIPSIS_RE.split(needle)
    out: list[str] = []
    for p in parts:
        if p in {"...", "…"}:
            continue
        p = _WS_RE.sub(" ", p).strip()
        if len(p) >= 12:
            out.append(p)
    return out


def is_grounded(
    evidence: str,
    lesson_raw_text: str,
    *,
    min_chars: int = _MIN_EVIDENCE_CHARS,
    allow_empty: bool = False,
) -> bool:
    """Return True if ``evidence`` is present in ``lesson_raw_text``.

    Empty evidence is grounded only when ``allow_empty=True`` (use for
    ``matched_status=none``). Positive claims must pass with a real quote.
    Stitched quotes using ``...`` must have **every** segment present (no
    sliding-window half-match shortcuts).
    """
    ev = (evidence or "").strip()
    if not ev:
        return bool(allow_empty)
    if len(ev) < min_chars:
        return False
    hay = normalize_for_grounding(lesson_raw_text)
    needle = normalize_for_grounding(ev)
    if not needle or not hay:
        return False

    if "..." in needle or "…" in needle:
        segments = _segment_evidence(needle)
        if len(segments) < 2:
            return False
        return all(seg in hay for seg in segments)

    if needle in hay:
        return True
    # Tolerate only tiny whitespace drift already handled by normalize.
    return False


def _quote_candidates(*quotes: str) -> list[str]:
    """Expand stitched quotes into verbatim pieces without loosening the check."""
    out: list[str] = []
    seen: set[str] = set()
    for raw in quotes:
        text = (raw or "").strip()
        if not text:
            continue
        pieces = [text]
        if _STITCH_RE.search(text):
            pieces.extend(p.strip() for p in _STITCH_RE.split(text) if p.strip())
        for piece in pieces:
            key = normalize_for_grounding(piece)
            if not key or key in seen:
                continue
            seen.add(key)
            out.append(piece)
    return out


def first_grounded_evidence(*quotes: str, lesson_raw_text: str) -> str | None:
    """Return the first candidate quote that is present in lesson text."""
    for piece in _quote_candidates(*quotes):
        if is_grounded(piece, lesson_raw_text, allow_empty=False):
            return piece
    return None


def page_from_evidence(evidence: str, lesson_raw_text: str) -> int | None:
    """Return the Stage-1 block page that contains ``evidence``, if any.

    Lesson raw text already carries publisher-agnostic ``(page N)`` headers
    from instructional blocks. This does not ask the LLM for a page and does
    not parse publisher-specific location strings.
    """
    needle = normalize_for_grounding(evidence)
    if not needle:
        return None
    if "..." in needle or "…" in needle:
        segments = _segment_evidence(needle)
        if not segments:
            return None
        needle = normalize_for_grounding(segments[0])
        if not needle:
            return None

    current_page: int | None = None
    current_parts: list[str] = []

    def _section_hit() -> int | None:
        if current_page is None or not current_parts:
            return None
        hay = normalize_for_grounding("\n".join(current_parts))
        if needle in hay:
            return current_page
        return None

    for line in (lesson_raw_text or "").splitlines():
        m = _PAGE_HEADER_RE.search(line)
        if m:
            hit = _section_hit()
            if hit is not None:
                return hit
            current_page = int(m.group(1))
            current_parts = [line]
        else:
            current_parts.append(line)
    return _section_hit()


def grounding_note(evidence: str, *, grounded: bool, allow_empty: bool = False) -> str:
    if not (evidence or "").strip():
        if allow_empty:
            return "no evidence required for none"
        return "empty evidence quote rejected for positive claim"
    if grounded:
        return "evidence quote found in lesson raw text"
    return "evidence quote NOT found in lesson raw text (possible fabrication)"


__all__ = [
    "first_grounded_evidence",
    "grounding_note",
    "is_grounded",
    "normalize_for_grounding",
    "page_from_evidence",
]
