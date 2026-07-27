"""Tests for ELA normalize sanitizers (pacing, code redact, verbatim quotes)."""

from __future__ import annotations

from veramynd_parser.models import InstructionalBlock, Lesson
from veramynd_parser.normalize.models import (
    DomainBlock,
    EvidenceItem,
    StudentActions,
    SubjectProfile,
    TaughtSkill,
    TeacherActions,
    VocabularyBlock,
    minimal_normalized_lesson,
)
from veramynd_parser.normalize.sanitize import (
    agenda_pacing,
    redact_standard_codes,
    resolve_verbatim_quote,
    sanitize_normalized_lesson,
)
from veramynd_parser.text_utils import parse_lesson_code


def _lesson_with_steps(code: str = "G1M2U2L3", steps: list[str] | None = None) -> Lesson:
    grade, module, unit, lesson_n = parse_lesson_code(code)
    from veramynd_parser.models import AgendaItem

    return Lesson(
        code=code,
        grade=grade,
        module=module,
        unit=unit,
        lesson=lesson_n,
        title="Lesson",
        page_start=1,
        page_end=2,
        agenda=[
            AgendaItem(section="Opening", letter="A", title="A", minutes=10),
            AgendaItem(section="Work Time", letter="A", title="B", minutes=50),
        ],
        instructional_blocks=[
            InstructionalBlock(
                section="Work Time",
                letter="A",
                title="Shared writing",
                page=1,
                steps=steps
                or [
                    "'What does the sun look like?'",
                    "Draw a quick sketch of what the moon looks like.",
                    "Students discuss using SL.1.1a and SL.1.1b protocols.",
                ],
            )
        ],
    )


def test_agenda_pacing_sums_minutes():
    assert agenda_pacing(_lesson_with_steps()) == "60 minutes"


def test_redact_standard_codes():
    text = "Participate using SL.1.1a, SL.1.1b, and L.1.6 during talk."
    out = redact_standard_codes(text)
    assert "SL.1.1a" not in out
    assert "L.1.6" not in out
    # Regression: the old code-by-code removal passed this test (it only checked
    # "Participate using" is a *prefix* of the output) while actually producing
    # "Participate using, and during talk." -- a dangling ", and" left over from
    # the list's own internal connectors. Assert the full clean string instead of
    # a substring, so a similar comma/connector artifact can't slip past silently.
    assert out == "Participate using during talk."


def test_redact_standard_codes_removes_a_whole_comma_and_list_atomically():
    """Regression: found in the real reference document's own lesson text
    (G1M2U2L6). Removing each code in a comma/and-joined list one at a time left
    the list's own commas and "and" behind as orphaned punctuation the cleanup
    regexes could not fully repair -- e.g. "Gather data on SL.1.1a, SL.1.1b,
    SL.1.4, and SL.1.6 using the checklist" became "Gather data on, and using
    the checklist." (the object of "on" silently vanished, leaving a comma with
    nothing before or after it). The whole list must be matched and removed as
    one atomic span so its internal connectors go with it."""
    text = (
        "Gather data on SL.1.1a, SL.1.1b, SL.1.4, and SL.1.6 using the Speaking "
        "and Listening Checklist."
    )
    out = redact_standard_codes(text)
    assert ",," not in out
    assert " on," not in out
    assert "for and" not in out
    assert out == "Gather data on using the Speaking and Listening Checklist."


def test_invented_moon_quote_replaced_or_dropped():
    lesson = _lesson_with_steps()
    lines = [
        "'What does the sun look like?'",
        "Draw a quick sketch of what the moon looks like.",
    ]
    corpus = "\n".join(lines)
    # Exact invented parallel — should not match sun line; may match moon sketch.
    resolved = resolve_verbatim_quote("'What does the moon look like?'", lines, corpus)
    # Not in source as that exact question → None or a high-ratio nearby line.
    assert resolved != "'What does the moon look like?'" or resolved is None
    # Sun quote must resolve exactly.
    assert resolve_verbatim_quote("'What does the sun look like?'", lines, corpus)


def test_sanitize_fixes_pacing_codes_and_bad_quote():
    lesson = _lesson_with_steps()
    norm = minimal_normalized_lesson(resource_id="G1M2U2L3").model_copy(
        update={
            "placement": minimal_normalized_lesson().placement.model_copy(
                update={"pacing": "single lesson"}
            ),
            "evidence": [
                EvidenceItem(
                    quote="'What does the sun look like?'",
                    location="Work Time A",
                    actor="student",
                    evidence_role="elicitation_check",
                    support="with_prompting",
                    supports_action=["oral_production"],
                ),
                EvidenceItem(
                    quote="'What does the moon look like?'",
                    location="Work Time A",
                    actor="student",
                    evidence_role="elicitation_check",
                    support="with_prompting",
                    supports_action=["oral_production"],
                ),
                EvidenceItem(
                    quote="Students discuss using SL.1.1a and SL.1.1b protocols.",
                    location="Closing",
                    actor="student",
                    evidence_role="directive_prompt",
                    support="with_prompting",
                    supports_action=["oral_production"],
                ),
            ],
            "student_actions": StudentActions(
                oral_production="Students answer look-like questions.",
            ),
            "domain": DomainBlock(primary="Speaking & Listening"),
            "what_is_taught": [
                TaughtSkill(
                    skill="describe sun and moon",
                    cognitive_demand="DOK1_recall_reproduction",
                )
            ],
            "teacher_actions": TeacherActions(with_prompting_and_support="yes"),
            "subject_profile": SubjectProfile(mode="interpretation", genre="n/a"),
            "objective": "Students describe the sun and moon.",
        }
    )
    fixed, warnings = sanitize_normalized_lesson(norm, lesson)
    assert fixed.placement.pacing == "60 minutes"
    assert all("SL." not in e.quote for e in fixed.evidence)
    assert all(e.quote != "'What does the moon look like?'" for e in fixed.evidence)
    assert any("sun look like" in e.quote.lower() for e in fixed.evidence)
    assert warnings


def test_sanitize_redacts_codes_from_materials_and_vocabulary():
    """Materials/vocabulary are re-stamped from Stage 1, cleaned, then redacted.

    Teaching-notes tips (During Work Time…) are dropped entirely — they are not
    materials. Codes embedded in real list items are still redacted.
    """
    lesson = _lesson_with_steps().model_copy(
        update={
            "materials": [
                "Chart paper",
                "During Work Time A, circulate and listen for students to use "
                "descriptive language. (SL.2.2)",
                "76",
                "Grade 1: Module 2: Unit 1: Lesson 4",
                "Reading checklist (see Assessment Overview) (RL.1.1)",
            ],
            "vocabulary": [
                "Post: Learning target and applicable anchor charts.",
                "observe (L)",
                "descriptive, using RL.1.1 language (R)",
            ],
        }
    )
    norm = minimal_normalized_lesson(resource_id="G1M2U2L3").model_copy(
        update={
            "materials": list(lesson.materials),
            "vocabulary": VocabularyBlock(new=lesson.vocabulary, review=[]),
            "evidence": [
                EvidenceItem(
                    quote="'What does the sun look like?'",
                    location="Work Time A",
                    actor="teacher",  # wrong — sanitizer must coerce to student
                    evidence_role="elicitation_check",
                    support="with_prompting",
                    supports_action=["oral_production"],
                )
            ],
        }
    )
    fixed, warnings = sanitize_normalized_lesson(norm, lesson)
    assert fixed.materials == ["Chart paper", "Reading checklist (see Assessment Overview)"]
    assert all("SL." not in m and "RL." not in m for m in fixed.materials)
    assert fixed.vocabulary.new == ["observe (L)"]
    assert len(fixed.vocabulary.review) == 1
    assert "RL." not in fixed.vocabulary.review[0]
    assert fixed.evidence[0].actor == "student"
    assert any("actor" in w for w in warnings)


def test_sanitize_aligns_teacher_model_actor():
    lesson = _lesson_with_steps()
    norm = minimal_normalized_lesson(resource_id="G1M2U2L3").model_copy(
        update={
            "evidence": [
                EvidenceItem(
                    quote="Draw a quick sketch of what the moon looks like.",
                    location="Work Time A",
                    actor="student",  # wrong for teacher_model
                    evidence_role="teacher_model",
                    support="not_applicable",
                    supports_action=[],
                ),
                EvidenceItem(
                    quote="'What does the sun look like?'",
                    location="Work Time A",
                    actor="student",
                    evidence_role="elicitation_check",
                    support="with_prompting",
                    supports_action=["oral_production"],
                ),
            ],
        }
    )
    fixed, warnings = sanitize_normalized_lesson(norm, lesson)
    model_ev = next(e for e in fixed.evidence if e.evidence_role == "teacher_model")
    assert model_ev.actor == "teacher"
    assert any("teacher_model" in w for w in warnings)


def test_sanitize_clears_readiness_supports_action():
    lesson = _lesson_with_steps(
        steps=[
            "Invite students to show a thumbs-up if they are ready to begin writing.",
            "'What does the sun look like?'",
        ]
    )
    norm = minimal_normalized_lesson(resource_id="G1M2U2L3").model_copy(
        update={
            "student_actions": StudentActions(
                oral_production="Answer questions about the sun.",
                written_production="Write about the story.",
            ),
            "evidence": [
                EvidenceItem(
                    quote="Invite students to show a thumbs-up if they are ready to begin writing.",
                    location="Closing",
                    actor="student",
                    evidence_role="directive_prompt",
                    support="with_prompting",
                    supports_action=["written_production"],
                ),
                EvidenceItem(
                    quote="'What does the sun look like?'",
                    location="Work Time A",
                    actor="student",
                    evidence_role="elicitation_check",
                    support="with_prompting",
                    supports_action=["oral_production"],
                ),
            ],
        }
    )
    fixed, warnings = sanitize_normalized_lesson(norm, lesson)
    ready = next(e for e in fixed.evidence if "thumbs-up" in e.quote)
    assert ready.supports_action == []
    assert fixed.student_actions.written_production == "NONE OBSERVED"
    assert any("readiness" in w for w in warnings)


def test_sanitize_canonicalizes_closing_location_to_stage1_block_id():
    """Regression: LLM wrote ``Closing A`` while Stage-1 always uses
    ``Closing and Assessment A`` — orphaning the evidence↔block join."""
    lesson = _lesson_with_steps(
        steps=[
            "'What does the sun look like?'",
            "Invite students to share one learning with a partner.",
        ]
    ).model_copy(
        update={
            "instructional_blocks": [
                InstructionalBlock(
                    section="Work Time",
                    letter="A",
                    title="Shared writing",
                    page=1,
                    steps=["'What does the sun look like?'"],
                ),
                InstructionalBlock(
                    section="Closing and Assessment",
                    letter="A",
                    title="Share",
                    page=2,
                    steps=["Invite students to share one learning with a partner."],
                ),
            ]
        }
    )
    norm = minimal_normalized_lesson(resource_id="G1M2U2L3").model_copy(
        update={
            "evidence": [
                EvidenceItem(
                    quote="Invite students to share one learning with a partner.",
                    location="Closing A",
                    actor="student",
                    evidence_role="directive_prompt",
                    support="with_prompting",
                    supports_action=["oral_production"],
                ),
                EvidenceItem(
                    quote="'What does the sun look like?'",
                    location="Work Time A",
                    actor="student",
                    evidence_role="elicitation_check",
                    support="with_prompting",
                    supports_action=["oral_production"],
                ),
            ],
        }
    )
    fixed, warnings = sanitize_normalized_lesson(norm, lesson)
    closing = next(e for e in fixed.evidence if "share one learning" in e.quote)
    assert closing.location == "Closing and Assessment A"
    assert any("Closing A" in w and "Closing and Assessment A" in w for w in warnings)
