"""P2: engine-side needs_review triggers (post-model, deterministic)."""

from __future__ import annotations

import re

# Rationale argues OR-list and separable/all-required at once (F9-type waffle).
_WAFFLE_OR = re.compile(
    r"(?i)\b("
    r"or[- ]?list|or[- ]like|any one|interchangeable|"
    r"one of the|under one .*umbrella|range[- ]of[- ]target"
    r")\b"
)
_WAFFLE_SEP = re.compile(
    r"(?i)\b("
    r"separable|all (?:four|required|of the)|"
    r"each names a distinct|must (?:all )?co-occur|"
    r"all collaborative acts|require all"
    r")\b"
)

# List-type standards where Partial + OR/separable language is the classic miss.
_LIST_STANDARD_CODES = frozenset(
    {
        "1.P.CP.1.d",
        "1.P.EICC.2.b",
        "1.L.V.1.b",
        "1.T.T.1.a",
    }
)


def looks_like_list_waffle(
    *,
    standard_code: str,
    rationale: str,
    matched_status: str,
) -> bool:
    """True when the model waffles OR-list vs separable on a list standard."""
    text = rationale or ""
    if not text.strip():
        return False
    has_or = bool(_WAFFLE_OR.search(text))
    has_sep = bool(_WAFFLE_SEP.search(text))
    if has_or and has_sep:
        return True
    code = (standard_code or "").strip()
    if code in _LIST_STANDARD_CODES and matched_status == "partial" and (has_or or has_sep):
        return True
    return False


def apply_engine_review_flags(
    *,
    needs_review: bool,
    review_reason: str,
    confidence: str,
    grounding_rejected: bool,
    standard_code: str,
    rationale: str,
    matched_status: str,
    invented_timing: bool = False,
) -> tuple[bool, str]:
    """Trip needs_review on low/medium confidence, grounding reject, list waffle, P5 timing.

    Overlay-set flags are preserved and merged with engine reasons.
    """
    reasons: list[str] = []
    existing = (review_reason or "").strip()
    if needs_review and existing:
        reasons.append(existing)
    elif needs_review:
        reasons.append("overlay review trigger")

    conf = (confidence or "").strip().lower()
    if conf in {"low", "medium"}:
        needs_review = True
        reasons.append(f"confidence={conf}")

    if grounding_rejected:
        needs_review = True
        reasons.append("grounding rejection")

    if looks_like_list_waffle(
        standard_code=standard_code,
        rationale=rationale,
        matched_status=matched_status,
    ):
        needs_review = True
        reasons.append("list-standard waffle (OR vs separable)")

    if invented_timing:
        needs_review = True
        reasons.append("invented while/after-reading timing (P5)")

    if not needs_review:
        return False, ""

    # Preserve order, drop duplicates.
    seen: set[str] = set()
    unique: list[str] = []
    for r in reasons:
        key = r.casefold()
        if key in seen:
            continue
        seen.add(key)
        unique.append(r)
    return True, "; ".join(unique)


__all__ = [
    "apply_engine_review_flags",
    "looks_like_list_waffle",
]
