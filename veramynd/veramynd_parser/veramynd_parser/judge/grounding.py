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


def grounding_note(evidence: str, *, grounded: bool, allow_empty: bool = False) -> str:
    if not (evidence or "").strip():
        if allow_empty:
            return "no evidence required for none"
        return "empty evidence quote rejected for positive claim"
    if grounded:
        return "evidence quote found in lesson raw text"
    return "evidence quote NOT found in lesson raw text (possible fabrication)"


__all__ = ["grounding_note", "is_grounded", "normalize_for_grounding"]
