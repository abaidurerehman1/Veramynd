"""Clean Stage-1 materials/vocabulary before stamping onto ELA normalize records.

These identity fields are system-stamped (not LLM-produced). PDF extraction often
drags page furniture and Teaching Notes "In advance" prep bullets into the lists,
and flattens New vs Review vocabulary. Cleaning here is defense-in-depth for
already-extracted Stage-1 JSON; extractors should also filter at source.
"""

from __future__ import annotations

import re

from ..text_utils import is_page_furniture, is_prep_or_tip_noise
from .models import VocabularyBlock

_REVIEW_MARKER = re.compile(r"\(r\)|\breview\b", re.I)
_SECTION_REVIEW = re.compile(r"^\s*Review\s*:\s*(.*)$", re.I)
_SECTION_NEW = re.compile(r"^\s*New\s*:\s*(.*)$", re.I)
_LEGEND_OR_HEADER = re.compile(
    r"^(?:Key\s*:|Vocabulary|N/A|(?:\(L\)|\(T\)|\(W\))\s*:)",
    re.I,
)


def clean_materials(raw: list[str]) -> list[str]:
    """Strip page furniture and In-advance prep bullets from a materials list."""
    out: list[str] = []
    seen: set[str] = set()
    for item in raw:
        t = (item or "").strip()
        if not t:
            continue
        if is_page_furniture(t) or is_prep_or_tip_noise(t):
            continue
        key = " ".join(t.split()).lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(t)
    return out


def split_vocabulary(raw: list[str]) -> VocabularyBlock:
    """Split Stage-1 flat vocab into new/review; drop furniture and prep noise.

    Respects source New vs Review when the extractor preserved section headers
    (standalone ``New`` / ``Review`` / ``New:`` / ``Review:`` lines, or
    ``Review: term`` prefixes) or when a term carries a whole-word ``review`` /
    ``(R)`` marker. Bare ``New`` / ``Review`` lines switch the section and are
    never added as vocabulary terms.

    Matches the ``(R)``/``Review`` marker as a whole word, not a bare substring —
    a vocabulary term that merely contains ``review`` (e.g. ``preview``,
    ``previewing``, ``reviewer``) must stay in ``new``.
    """
    new: list[str] = []
    review: list[str] = []
    section: str | None = None  # "new" | "review" | None

    def _add(term: str, bucket: str | None) -> None:
        raw = term.strip()
        if not raw:
            return
        # Check noise on the raw line (leading bullets matter for prep detection).
        if is_page_furniture(raw) or is_prep_or_tip_noise(raw):
            return
        t = raw.strip("-–—•").strip()
        if not t:
            return
        if _LEGEND_OR_HEADER.match(t):
            return
        target = review if bucket == "review" else new
        other = new if bucket == "review" else review
        key = " ".join(t.split()).lower()
        if any(" ".join(x.split()).lower() == key for x in target):
            return
        other[:] = [x for x in other if " ".join(x.split()).lower() != key]
        target.append(t)

    for term in raw:
        t = (term or "").strip()
        if not t:
            continue

        if re.fullmatch(r"New\s*:?", t, flags=re.I):
            section = "new"
            continue
        if re.fullmatch(r"Review\s*:?", t, flags=re.I):
            section = "review"
            continue

        m_rev = _SECTION_REVIEW.match(t)
        if m_rev:
            section = "review"
            rest = (m_rev.group(1) or "").strip()
            if rest:
                _add(rest, "review")
            continue

        m_new = _SECTION_NEW.match(t)
        if m_new:
            section = "new"
            rest = (m_new.group(1) or "").strip()
            if rest:
                _add(rest, "new")
            continue

        if _REVIEW_MARKER.search(t):
            _add(t, "review")
            continue

        if section == "review":
            _add(t, "review")
        else:
            _add(t, "new" if section == "new" else "new")

    return VocabularyBlock(new=new, review=review)


__all__ = [
    "clean_materials",
    "split_vocabulary",
]
