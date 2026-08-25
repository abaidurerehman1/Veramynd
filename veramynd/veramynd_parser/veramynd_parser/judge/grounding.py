"""Evidence grounding check — reject fabricated judge quotes (zero LLM cost)."""

from __future__ import annotations

import re
import unicodedata


_WS_RE = re.compile(r"\s+")
_ELLIPSIS_RE = re.compile(r"(\.\.\.|…)")
_SEMI_RE = re.compile(r"\s*;\s*")
# P10: model-inserted editorial glosses, not lesson text.
_EDITORIAL_BRACKET_RE = re.compile(r"\[[^\]]*\]")
_UNCLOSED_BRACKET_RE = re.compile(r"\[[^\]]*$")
_SPACE_BEFORE_PUNCT_RE = re.compile(r"\s+([.,;:!?])")
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
_MIN_SEGMENT_CHARS = 12
_PAGE_HEADER_RE = re.compile(r"(?i)\(\s*page\s+(\d+)\s*\)")
_STITCH_RE = re.compile(r"\s+/\s+")


def normalize_for_grounding(text: str) -> str:
    """Lowercase, unify quotes/dashes, collapse whitespace and bullet prefixes."""
    s = unicodedata.normalize("NFKC", text or "")
    s = s.translate(_TRANS)
    s = s.lower()
    # Italics/markdown underscores and blank lines (________) → space.
    s = s.replace("_", " ")
    # Drop quote marks so 'frame' and "frame" match the same lesson span.
    s = s.replace("'", " ").replace('"', " ")
    s = re.sub(r"(?m)^\s*-\s*", " ", s)
    s = _WS_RE.sub(" ", s).strip()
    return s


def _segment_ellipsis(chunk: str) -> list[str]:
    """Split one chunk on ellipsis; drop empty/short pieces."""
    parts = _ELLIPSIS_RE.split(chunk)
    out: list[str] = []
    for p in parts:
        if p in {"...", "…"}:
            continue
        p = _WS_RE.sub(" ", p).strip()
        if len(p) >= _MIN_SEGMENT_CHARS:
            out.append(p)
    return out


def _multi_quote_segments(needle: str) -> list[str]:
    """Split stitched multi-quote evidence on ``;`` and ellipsis (P8).

    Models often join non-contiguous verbatim spans with ``;`` or ``…``.
    Each resulting segment must be grounded independently.
    ``needle`` should already be normalize_for_grounding'd when used for
    membership checks.
    """
    chunks = _SEMI_RE.split(needle) if ";" in needle else [needle]
    out: list[str] = []
    for chunk in chunks:
        chunk = _WS_RE.sub(" ", (chunk or "").strip()).strip()
        if not chunk:
            continue
        if "..." in chunk or "…" in chunk:
            out.extend(_segment_ellipsis(chunk))
        elif len(chunk) >= _MIN_SEGMENT_CHARS:
            out.append(chunk)
    return out


def _raw_stitch_pieces(text: str) -> list[str]:
    """Split raw evidence on ``;`` / ellipsis, preserving original wording."""
    chunks = _SEMI_RE.split(text) if ";" in text else [text]
    out: list[str] = []
    for chunk in chunks:
        chunk = (chunk or "").strip()
        if not chunk:
            continue
        if "..." in chunk or "…" in chunk:
            for part in _ELLIPSIS_RE.split(chunk):
                if part in {"...", "…"}:
                    continue
                part = part.strip()
                if len(normalize_for_grounding(part)) >= _MIN_SEGMENT_CHARS:
                    out.append(part)
        elif len(normalize_for_grounding(chunk)) >= _MIN_SEGMENT_CHARS:
            out.append(chunk)
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
    Stitched quotes using ``;`` or ``...``/``…`` must have **every** segment
    present (no sliding-window half-match shortcuts). A contiguous span that
    itself contains ``;`` still passes via the whole-string check first.
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

    # Contiguous match (includes a single quote that happens to contain ';').
    if needle in hay:
        return True

    has_stitch = ";" in needle or "..." in needle or "…" in needle
    if not has_stitch:
        return False

    segments = _multi_quote_segments(needle)
    if len(segments) >= 2:
        return all(seg in hay for seg in segments)
    # Internal '...' inside one otherwise-real span (not a multi-quote stitch).
    if len(segments) == 1:
        return segments[0] in hay
    return False


def scrub_editorial_brackets(text: str) -> str:
    """P10: remove model ``[editorial notes]``; keep only candidate quote text."""
    s = _EDITORIAL_BRACKET_RE.sub(" ", text or "")
    s = _UNCLOSED_BRACKET_RE.sub(" ", s)
    s = _WS_RE.sub(" ", s).strip()
    s = _SPACE_BEFORE_PUNCT_RE.sub(r"\1", s)
    return s.strip()


def _longest_verbatim_window(
    text: str,
    lesson_raw_text: str,
    *,
    min_chars: int = _MIN_EVIDENCE_CHARS,
) -> str | None:
    """Longest contiguous word-span of ``text`` that appears in the lesson."""
    words = (text or "").split()
    if not words:
        return None
    hay = normalize_for_grounding(lesson_raw_text)
    if not hay:
        return None
    best: str | None = None
    best_len = 0
    n = len(words)
    for i in range(n):
        for j in range(n, i, -1):
            piece = " ".join(words[i:j])
            if len(piece) < min_chars:
                break
            if len(piece) <= best_len:
                break
            if normalize_for_grounding(piece) in hay:
                best = piece
                best_len = len(piece)
                break
    return best


def clean_evidence_quotes(*quotes: str, lesson_raw_text: str) -> list[str]:
    """Expand quotes with P10 scrub + longest verbatim repair candidates."""
    out: list[str] = []
    seen: set[str] = set()

    def _add(piece: str) -> None:
        text = (piece or "").strip()
        if not text:
            return
        key = normalize_for_grounding(text)
        if not key or key in seen:
            return
        seen.add(key)
        out.append(text)

    for raw in quotes:
        text = (raw or "").strip()
        if not text:
            continue
        _add(text)
        scrubbed = scrub_editorial_brackets(text)
        if scrubbed:
            _add(scrubbed)
            window = _longest_verbatim_window(scrubbed, lesson_raw_text)
            if window:
                _add(window)
        elif text:
            window = _longest_verbatim_window(text, lesson_raw_text)
            if window:
                _add(window)
    return out


def _quote_candidates(*quotes: str) -> list[str]:
    """Expand stitched quotes into verbatim pieces without loosening the check."""
    out: list[str] = []
    seen: set[str] = set()
    for raw in quotes:
        text = (raw or "").strip()
        if not text:
            continue
        pieces = [text]
        scrubbed = scrub_editorial_brackets(text)
        if scrubbed and scrubbed != text:
            pieces.append(scrubbed)
        if _STITCH_RE.search(text):
            pieces.extend(p.strip() for p in _STITCH_RE.split(text) if p.strip())
        for base in (text, scrubbed):
            if base and (";" in base or "..." in base or "…" in base):
                pieces.extend(_raw_stitch_pieces(base))
        for piece in pieces:
            key = normalize_for_grounding(piece)
            if not key or key in seen:
                continue
            seen.add(key)
            out.append(piece)
    return out


def expand_short_exact_hit(
    evidence: str,
    lesson_raw_text: str,
    *,
    min_chars: int = _MIN_EVIDENCE_CHARS,
    min_needle_chars: int = _MIN_SEGMENT_CHARS,
) -> str | None:
    """Expand a short but exact lesson substring to a grounded ≥min_chars window.

    Publisher-agnostic repair: models often quote a sentence frame or TDQ
    shorter than the anti-fabrication floor (e.g. ``At the end …``). If that
    short span is a real contiguous hit in the lesson, widen to neighboring
    words until the quote clears ``min_chars``. Fabricated short strings that
    are not in the lesson still fail.
    """
    ev = (evidence or "").strip()
    if not ev or len(ev) >= min_chars:
        return None
    needle = normalize_for_grounding(ev)
    if len(needle) < min_needle_chars:
        return None
    hay = normalize_for_grounding(lesson_raw_text)
    if not hay or needle not in hay:
        return None

    words = (lesson_raw_text or "").split()
    n = len(words)
    if not n:
        return None

    # Prefer the shortest word-span whose normalized form contains the needle,
    # then grow outward until the raw quote meets min_chars.
    best_ij: tuple[int, int] | None = None
    best_span = n + 1
    for i in range(n):
        for j in range(i + 1, n + 1):
            span = j - i
            if span >= best_span:
                break
            piece = " ".join(words[i:j])
            norm = normalize_for_grounding(piece)
            if needle in norm:
                best_ij = (i, j)
                best_span = span
                break
    if best_ij is None:
        return None

    i, j = best_ij
    while (j - i) < n and len(" ".join(words[i:j])) < min_chars:
        # Grow forward first, then backward, keeping the original hit inside.
        if j < n:
            j += 1
        elif i > 0:
            i -= 1
        else:
            break
    while i > 0 and len(" ".join(words[i:j])) < min_chars:
        i -= 1

    expanded = " ".join(words[i:j]).strip()
    if len(expanded) < min_chars:
        return None
    if is_grounded(expanded, lesson_raw_text, allow_empty=False, min_chars=min_chars):
        return expanded
    return None


def first_grounded_evidence(*quotes: str, lesson_raw_text: str) -> str | None:
    """Return the first candidate quote that is present in lesson text.

    Applies P10 scrub/repair (strip ``[editorial notes]``, recover the longest
    verbatim window) before the P8 multi-quote split check. Short exact lesson
    hits (sentence frames / TDQs under the min-length floor) are expanded to a
    surrounding verbatim window when possible.
    """
    cleaned = clean_evidence_quotes(*quotes, lesson_raw_text=lesson_raw_text)
    for piece in _quote_candidates(*cleaned):
        if is_grounded(piece, lesson_raw_text, allow_empty=False):
            return piece
        expanded = expand_short_exact_hit(piece, lesson_raw_text)
        if expanded:
            return expanded
    # Last resort: longest grounded window over any original quote.
    for raw in quotes:
        window = _longest_verbatim_window(
            scrub_editorial_brackets(raw) or (raw or ""),
            lesson_raw_text,
        )
        if window and is_grounded(window, lesson_raw_text, allow_empty=False):
            return window
        expanded = expand_short_exact_hit(
            scrub_editorial_brackets(raw) or (raw or ""),
            lesson_raw_text,
        )
        if expanded:
            return expanded
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
    if ";" in needle or "..." in needle or "…" in needle:
        segments = _multi_quote_segments(needle)
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
    "clean_evidence_quotes",
    "expand_short_exact_hit",
    "first_grounded_evidence",
    "grounding_note",
    "is_grounded",
    "normalize_for_grounding",
    "page_from_evidence",
    "scrub_editorial_brackets",
]
