"""P6 coverage pass: inject activity-driven standards the shortlist dropped.

Retrieve ranking is not changed. After the judge takes the first N retrieve
hits, this pass appends collaboration / feedback / present codes when the
lesson text actually shows those student tasks. Codes are taken from the
retrieve pool (candidates + reranked + rrf) when present, else from the
normalized standards dir.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Iterable

MAX_COVERAGE_EXTRAS = 8

# GA overlay instances of the activity families — not a publisher if-tree.
_FEEDBACK_CODES = ("1.P.EICC.4.f", "1.P.CP.1.c")
_PRESENT_CODES = ("1.P.CP.2.a",)

_FEEDBACK_LESSON = re.compile(
    r"(?i)\bprovide(?:\s+\w+){0,8}\s+feedback\b"
    r"|\bgiv(?:e|ing) feedback\b"
    r"|\breceiv(?:e|ing) feedback\b"
    r"|\bpeer (?:feedback|critique|review)\b"
    r"|\bfeedback\b.{0,40}\b(?:classmates?|partners?|peers?)\b"
)
_PRESENT_LESSON = re.compile(
    r"(?i)\bpresent(?:s|ing|ed)?\b.{0,40}\b(?:class|group|audience|partner)"
    r"|\bshare (?:with|to) (?:the )?(?:class|whole group|small group|group|audience)\b"
    r"|\bspeak(?:ing)? (?:aloud|to the class)\b"
    r"|\bpartners? protocol\b"
    r"|\bshare .{0,50}\b(?:writing|work|poem|verse)\b"
)


@dataclass(frozen=True)
class CoverageFamily:
    name: str
    lesson_re: re.Pattern[str]
    known_codes: tuple[str, ...]


FAMILIES: tuple[CoverageFamily, ...] = (
    CoverageFamily(
        name="feedback",
        lesson_re=_FEEDBACK_LESSON,
        known_codes=_FEEDBACK_CODES,
    ),
    CoverageFamily(
        name="present",
        lesson_re=_PRESENT_LESSON,
        known_codes=_PRESENT_CODES,
    ),
)


def detect_activity_families(lesson_text: str) -> list[CoverageFamily]:
    text = lesson_text or ""
    return [fam for fam in FAMILIES if fam.lesson_re.search(text)]


def load_retrieve_pool(retrieve_data: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Map standard_code → candidate row. Shortlist wins, then reranked, then rrf."""
    pool: dict[str, dict[str, Any]] = {}
    for key in ("rrf_candidates", "reranked_candidates", "candidates"):
        rows = retrieve_data.get(key) or []
        if not isinstance(rows, list):
            continue
        for row in rows:
            if not isinstance(row, dict):
                continue
            code = (row.get("standard_code") or "").strip()
            if code:
                pool[code] = row
    return pool


def _codes_for_family(family: CoverageFamily) -> list[str]:
    """Known overlay instances only — do not scan the retrieve catalog."""
    return list(family.known_codes)


def apply_activity_coverage_pass(
    selected: list[dict[str, Any]],
    *,
    lesson_text: str,
    pool: dict[str, dict[str, Any]],
    available_codes: Iterable[str] | None = None,
) -> tuple[list[dict[str, Any]], list[str]]:
    """Append activity-driven codes missing from ``selected``. Ranking unchanged.

    ``available_codes`` is the standards-dir set; a known code not in the
    retrieve pool is still injected when that file exists.
    """
    families = detect_activity_families(lesson_text)
    if not families:
        return list(selected), []

    have = {
        (c.get("standard_code") or "").strip()
        for c in selected
        if isinstance(c, dict)
    }
    available = {str(c).strip() for c in (available_codes or []) if str(c).strip()}
    extras: list[dict[str, Any]] = []
    injected: list[str] = []

    for family in families:
        for code in _codes_for_family(family):
            if code in have:
                continue
            if len(extras) >= MAX_COVERAGE_EXTRAS:
                break
            row = dict(pool.get(code) or {"standard_code": code})
            row["standard_code"] = code
            row["coverage_pass"] = True
            row["coverage_family"] = family.name
            if code not in pool and (
                not available or code not in available
            ):
                continue
            extras.append(row)
            injected.append(code)
            have.add(code)

    if not extras:
        return list(selected), []
    return list(selected) + extras, injected
