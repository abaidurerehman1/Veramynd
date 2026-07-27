"""Post-LLM sanitizers for ELA curriculum-normalization records.

Enforces blank-template / README rules the model often misses:
1. ``placement.pacing`` = sum(agenda minutes) + \" minutes\" when available
2. No CCSS-style standard codes in free text (esp. evidence quotes)
3. Evidence quotes must be verbatim spans of Stage-1 lesson text
4. ``actor`` matches the performer implied by ``evidence_role``
5. Materials/vocabulary are re-stamped clean from Stage 1 (no page furniture /
   In-advance prep bullets; New vs Review preserved when present)
6. ``evidence[].location`` joins to Stage-1 ``{section} {letter}`` block IDs
   (e.g. LLM ``Closing A`` → Stage-1 ``Closing and Assessment A``)
"""

from __future__ import annotations

import re
from difflib import SequenceMatcher

from ..models import Lesson
from .identity_fields import clean_materials, split_vocabulary
from .models import (
    NONE_OBSERVED,
    STUDENT_ACTION_KEYS,
    EvidenceItem,
    NormalizedLesson,
    StudentActions,
    VocabularyBlock,
)

# CCSS-style codes (and close cousins) that must not appear in the scorable record.
_ONE_CODE = r"(?:RL|RI|RF|W|SL|L)\.\d+[a-zA-Z0-9.]*"
# A whole comma/and-joined LIST of codes ("SL.1.1a, SL.1.1b, and SL.1.4"), matched
# as a single atomic span rather than one code at a time. Real lesson text lists
# multiple codes per assessment note (e.g. "Gather data on SL.1.1a, SL.1.1b, SL.1.4,
# and SL.1.6 using the checklist"); removing each code separately leaves the list's
# own internal commas and "and" behind as orphaned punctuation the cleanup regexes
# below cannot fully repair (observed output: "Gather data on, and using the
# checklist." -- the object of "on" silently disappears along with the codes,
# leaving a comma with nothing before or after it). Matching the whole list in one
# shot removes its internal connectors along with the codes it was connecting.
_STANDARD_CODE_RE = re.compile(
    rf"\b{_ONE_CODE}(?:\s*,\s*{_ONE_CODE})*(?:\s*,?\s*and\s+{_ONE_CODE})?\b"
)

# Minimum similarity to accept a near-match replacement for a non-verbatim quote.
_VERBATIM_RATIO = 0.88

# evidence_role → performer of the act the quote evidences (not who utters it).
_ROLE_DEFAULT_ACTOR: dict[str, str] = {
    "directive_prompt": "student",
    "elicitation_check": "student",
    "student_production": "student",
    "teacher_model": "teacher",
    "teacher_scribe": "teacher",
}

# Readiness / management prompts must not carry content supports_action
# (v2 prompt worked example: thumbs-up "ready to begin writing" → []).
_READINESS_MANAGEMENT = re.compile(
    r"(?:"
    r"thumbs[- ]up.{0,80}ready to begin"
    r"|ready to begin (?:writing|drawing|reading|listening)"
    r"|are you ready\b"
    r"|show (?:me |a )?thumbs[- ]up if (?:you|they) are ready"
    r")",
    re.I | re.S,
)

# Leading "{section} {letter}" join key used by Stage-1 instructional_blocks.
_LOCATION_BLOCK = re.compile(
    r"^\s*(?P<section>.+?)\s+(?P<letter>[A-Z])\b(?P<rest>.*)$"
)


def agenda_pacing(lesson: Lesson) -> str:
    """Duration string from Stage-1 agenda minutes, or empty if unknown."""
    if not lesson.agenda:
        return ""
    total = sum(a.minutes or 0 for a in lesson.agenda)
    if total <= 0:
        return ""
    return f"{total} minutes"


def redact_standard_codes(text: str) -> str:
    """Remove standard codes; collapse leftover whitespace/punctuation debris."""
    if not text:
        return text
    cleaned = _STANDARD_CODE_RE.sub("", text)
    cleaned = re.sub(r"\s{2,}", " ", cleaned)
    cleaned = re.sub(r"\s+([,;:.])", r"\1", cleaned)
    cleaned = re.sub(r"\(\s*[,;]*\s*\)", "", cleaned)
    # "using SL.1.1a and SL.1.1b protocols" → "using  and  protocols" → "using protocols"
    cleaned = re.sub(r"\b(using|including|with|via)\s+and\s+", r"\1 ", cleaned, flags=re.I)
    cleaned = re.sub(r",\s*,+", ",", cleaned)
    cleaned = re.sub(r"\band\s+and\b", "and", cleaned, flags=re.I)
    cleaned = re.sub(r"\s{2,}", " ", cleaned).strip(" ,;")
    return cleaned


def _norm_ws(text: str) -> str:
    return " ".join((text or "").split())


def lesson_source_lines(lesson: Lesson) -> list[str]:
    """Candidate verbatim spans from the Stage-1 lesson."""
    lines: list[str] = []
    if lesson.title:
        lines.append(lesson.title)
    for t in lesson.learning_targets:
        if t.text:
            lines.append(t.text)
    for a in lesson.agenda:
        if a.title:
            lines.append(a.title)
    for b in lesson.instructional_blocks:
        if b.title:
            lines.append(b.title)
        for step in b.steps:
            if step and step.strip():
                lines.append(step.strip())
    for term in lesson.vocabulary:
        if term and term.strip():
            lines.append(term.strip())
    # Deduplicate while preserving order.
    seen: set[str] = set()
    out: list[str] = []
    for line in lines:
        key = _norm_ws(line).lower()
        if key and key not in seen:
            seen.add(key)
            out.append(line)
    return out


def lesson_source_corpus(lesson: Lesson) -> str:
    return "\n".join(lesson_source_lines(lesson))


def quote_is_verbatim(quote: str, corpus: str) -> bool:
    """True if quote (whitespace-normalized) appears in the source corpus."""
    q = _norm_ws(quote)
    if not q:
        return False
    c = _norm_ws(corpus)
    if q in c:
        return True
    # Allow surrounding quotes difference.
    stripped = q.strip("\"'")
    return bool(stripped) and stripped in c


def resolve_verbatim_quote(quote: str, source_lines: list[str], corpus: str) -> str | None:
    """Return an exact source span, or None if the quote cannot be grounded."""
    redacted = redact_standard_codes(quote)
    if not _norm_ws(redacted):
        return None
    if quote_is_verbatim(redacted, corpus):
        # Prefer the original source casing/punctuation when an exact line matches.
        target = _norm_ws(redacted).lower()
        for line in source_lines:
            if _norm_ws(line).lower() == target:
                return line
            if _norm_ws(line).lower() == target.strip("\"'"):
                return line
        return redacted

    best_line = ""
    best_ratio = 0.0
    qn = _norm_ws(redacted).lower()
    for line in source_lines:
        ln = _norm_ws(line).lower()
        if not ln:
            continue
        # Quote is a contiguous span of a source step (or vice versa): accept exactly.
        if qn in ln:
            return line
        if ln in qn and len(ln) >= 24:
            return line
        ratio = SequenceMatcher(None, qn, ln).ratio()
        if ratio > best_ratio:
            best_ratio = ratio
            best_line = line
    if best_ratio >= _VERBATIM_RATIO and best_line:
        return best_line
    return None


def sanitize_evidence_against_source(
    evidence: list[EvidenceItem],
    lesson: Lesson,
) -> tuple[list[EvidenceItem], list[str]]:
    """Redact codes + enforce verbatim quotes. Returns (kept, warnings)."""
    lines = lesson_source_lines(lesson)
    corpus = "\n".join(lines)
    kept: list[EvidenceItem] = []
    warnings: list[str] = []
    for i, item in enumerate(evidence):
        resolved = resolve_verbatim_quote(item.quote, lines, corpus)
        if resolved is None:
            warnings.append(
                f"dropped evidence[{i}] — not verbatim in source: {item.quote[:80]!r}"
            )
            continue
        quote = redact_standard_codes(resolved)
        if not _norm_ws(quote):
            warnings.append(f"dropped evidence[{i}] — empty after code redaction")
            continue
        if quote != item.quote:
            warnings.append(
                f"repaired evidence[{i}] quote to verbatim source span"
            )
        kept.append(
            item.model_copy(
                update={
                    "quote": quote,
                    "location": redact_standard_codes(item.location),
                    "qualifiers": [redact_standard_codes(q) for q in item.qualifiers],
                }
            )
        )
    return kept, warnings


def align_actor_to_evidence_role(
    evidence: list[EvidenceItem],
) -> tuple[list[EvidenceItem], list[str]]:
    """Coerce actor to the performer implied by evidence_role.

    The student-actor gate scores the performer of the act, not the speaker.
    directive/elicitation/student_production → student; teacher_model/scribe →
    teacher. assessment_item and shared/unspecified are left alone.
    """
    warnings: list[str] = []
    out: list[EvidenceItem] = []
    for i, item in enumerate(evidence):
        expected = _ROLE_DEFAULT_ACTOR.get(item.evidence_role)
        if expected is None or item.actor == expected:
            out.append(item)
            continue
        warnings.append(
            f"evidence[{i}] actor {item.actor!r} -> {expected!r} "
            f"(from evidence_role={item.evidence_role!r})"
        )
        out.append(item.model_copy(update={"actor": expected}))
    return out, warnings


def clear_readiness_supports_action(
    evidence: list[EvidenceItem],
) -> tuple[list[EvidenceItem], list[str]]:
    """Strip content supports_action from pure readiness/management prompts."""
    warnings: list[str] = []
    out: list[EvidenceItem] = []
    for i, item in enumerate(evidence):
        if not item.supports_action or not _READINESS_MANAGEMENT.search(item.quote or ""):
            out.append(item)
            continue
        warnings.append(
            f"evidence[{i}] cleared supports_action {item.supports_action!r} "
            f"(readiness/management prompt)"
        )
        out.append(item.model_copy(update={"supports_action": []}))
    return out, warnings


def stage1_block_ids(lesson: Lesson) -> set[str]:
    """Canonical join keys: ``\"{section} {letter}\"`` from Stage-1 blocks."""
    return {
        f"{b.section} {b.letter}"
        for b in lesson.instructional_blocks
        if (b.section or "").strip() and (b.letter or "").strip()
    }


def _resolve_stage1_section(hint: str, letter: str, lesson: Lesson) -> str | None:
    """Map an LLM location section hint to the Stage-1 section for that letter.

    Exact match wins. Otherwise accept a unique Stage-1 section for the same
    letter whose name starts with the hint (``Closing`` → ``Closing and
    Assessment``). Ambiguous matches are left unresolved.
    """
    hint = (hint or "").strip()
    letter = (letter or "").strip()
    if not hint or not letter:
        return None

    by_letter = [
        (b.section or "").strip()
        for b in lesson.instructional_blocks
        if (b.letter or "").strip() == letter and (b.section or "").strip()
    ]
    if not by_letter:
        return None

    exact = [s for s in by_letter if s == hint]
    if exact:
        return exact[0]

    # Prefix expansion: "Closing" → "Closing and Assessment" (unique for letter).
    prefixed = [
        s
        for s in by_letter
        if s.startswith(hint + " ") or s.startswith(hint + " and ")
    ]
    # Also allow trailing punctuation / ampersand variants after the hint.
    if not prefixed:
        prefixed = [
            s
            for s in by_letter
            if s.startswith(hint) and len(s) > len(hint) and s[len(hint)] in " &/"
        ]
    uniq = sorted(set(prefixed))
    if len(uniq) == 1:
        return uniq[0]
    return None


def canonicalize_evidence_locations(
    evidence: list[EvidenceItem],
    lesson: Lesson,
) -> tuple[list[EvidenceItem], list[str]]:
    """Rewrite ``evidence[].location`` to Stage-1 ``{section} {letter}`` IDs.

    Chunk / retrieval joins must use Stage-1 block IDs as ground truth. The LLM
    sometimes shortens section names (observed: ``Closing A`` instead of
    ``Closing and Assessment A``), which orphans the pointer.
    """
    warnings: list[str] = []
    ids = stage1_block_ids(lesson)
    out: list[EvidenceItem] = []
    for i, item in enumerate(evidence):
        loc = (item.location or "").strip()
        if not loc:
            warnings.append(f"evidence[{i}] location is empty — cannot join to Stage-1")
            out.append(item)
            continue

        m = _LOCATION_BLOCK.match(loc)
        if not m:
            warnings.append(
                f"evidence[{i}] location {loc!r} has no '{{section}} {{letter}}' prefix"
            )
            out.append(item)
            continue

        hint = m.group("section").strip()
        letter = m.group("letter").strip()
        rest = (m.group("rest") or "").strip()
        exact_id = f"{hint} {letter}"
        if exact_id in ids:
            # Already joins; normalize whitespace / drop stray rest unless needed.
            canonical = exact_id if not rest else f"{exact_id} {rest}".strip()
            if canonical != loc:
                warnings.append(
                    f"evidence[{i}] location {loc!r} -> {canonical!r} (whitespace)"
                )
                out.append(item.model_copy(update={"location": canonical}))
            else:
                out.append(item)
            continue

        resolved = _resolve_stage1_section(hint, letter, lesson)
        if resolved is None:
            warnings.append(
                f"evidence[{i}] location {loc!r} does not join any Stage-1 block "
                f"(known: {sorted(ids)})"
            )
            out.append(item)
            continue

        canonical = f"{resolved} {letter}"
        if rest:
            canonical = f"{canonical} {rest}".strip()
        warnings.append(
            f"evidence[{i}] location {loc!r} -> {canonical!r} (Stage-1 block id)"
        )
        out.append(item.model_copy(update={"location": canonical}))
    return out, warnings


def demote_uncovered_actions(norm: NormalizedLesson) -> NormalizedLesson:
    """Re-apply coverage rule after evidence drops."""
    covered: set[str] = set()
    for item in norm.evidence:
        covered.update(item.supports_action)

    sa = norm.student_actions.model_dump()
    demoted: list[str] = []
    for key in STUDENT_ACTION_KEYS:
        val = (sa.get(key) or "").strip()
        if val and val != NONE_OBSERVED and key not in covered:
            sa[key] = NONE_OBSERVED
            demoted.append(key)
    if not demoted:
        return norm
    return norm.model_copy(update={"student_actions": StudentActions(**sa)})


def sanitize_normalized_lesson(
    norm: NormalizedLesson,
    lesson: Lesson,
) -> tuple[NormalizedLesson, list[str]]:
    """Apply all post-LLM sanitizers. Returns (record, warnings)."""
    warnings: list[str] = []

    pacing = agenda_pacing(lesson)
    if pacing and norm.placement.pacing != pacing:
        warnings.append(
            f"pacing set from agenda minutes: {pacing!r} (was {norm.placement.pacing!r})"
        )
        norm = norm.model_copy(
            update={"placement": norm.placement.model_copy(update={"pacing": pacing})}
        )

    evidence, ev_warnings = sanitize_evidence_against_source(list(norm.evidence), lesson)
    warnings.extend(ev_warnings)
    if not evidence:
        raise ValueError(
            f"{norm.resource_id}: no evidence quotes remain after verbatim/code sanitization"
        )

    evidence, actor_warnings = align_actor_to_evidence_role(evidence)
    warnings.extend(actor_warnings)

    evidence, readiness_warnings = clear_readiness_supports_action(evidence)
    warnings.extend(readiness_warnings)

    evidence, loc_warnings = canonicalize_evidence_locations(evidence, lesson)
    warnings.extend(loc_warnings)

    taught = [
        s.model_copy(update={"skill": redact_standard_codes(s.skill)})
        for s in norm.what_is_taught
    ]
    sa = norm.student_actions.model_dump()
    for key in STUDENT_ACTION_KEYS:
        sa[key] = redact_standard_codes(sa[key])

    # Re-stamp identity lists from Stage 1 so repair/normalize always drop
    # page furniture and In-advance prep bullets, and respect New vs Review.
    materials = [redact_standard_codes(m) for m in clean_materials(list(lesson.materials))]
    vocab = split_vocabulary(list(lesson.vocabulary))
    vocabulary = VocabularyBlock(
        new=[redact_standard_codes(v) for v in vocab.new],
        review=[redact_standard_codes(v) for v in vocab.review],
    )

    norm = norm.model_copy(
        update={
            "objective": redact_standard_codes(norm.objective),
            "what_is_taught": taught,
            "what_is_NOT_taught": [redact_standard_codes(x) for x in norm.what_is_NOT_taught],
            "student_actions": StudentActions(**sa),
            "evidence": evidence,
            "notes": redact_standard_codes(norm.notes),
            "teacher_actions": norm.teacher_actions.model_copy(
                update={
                    "direct_instruction": redact_standard_codes(
                        norm.teacher_actions.direct_instruction
                    ),
                    "prompts_that_cue_student_response": [
                        redact_standard_codes(p)
                        for p in norm.teacher_actions.prompts_that_cue_student_response
                    ],
                }
            ),
            "materials": materials,
            "vocabulary": vocabulary,
        }
    )
    before = {
        k
        for k in STUDENT_ACTION_KEYS
        if getattr(norm.student_actions, k) != NONE_OBSERVED
        and getattr(norm.student_actions, k).strip()
    }
    norm = demote_uncovered_actions(norm)
    after = {
        k
        for k in STUDENT_ACTION_KEYS
        if getattr(norm.student_actions, k) != NONE_OBSERVED
        and getattr(norm.student_actions, k).strip()
    }
    lost = sorted(before - after)
    if lost:
        warnings.append(f"demoted unproven student_actions after evidence repair: {lost}")

    # Re-validate via model (coverage / conditionals).
    return NormalizedLesson.model_validate(norm.model_dump()), warnings
