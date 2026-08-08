"""Tests for ELA normalize sanitizers (pacing, code redact, verbatim quotes)."""

from __future__ import annotations

import pytest

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
    sanitize_evidence_against_source,
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


def test_redact_standard_codes_removes_kindergarten_ccss():
    """K-grade codes (RL.K.1) must redact — digit-only patterns leak them."""
    text = "Ask and answer questions about RL.K.1 and SL.K.1a during talk."
    out = redact_standard_codes(text)
    assert "RL.K" not in out
    assert "SL.K" not in out
    assert "RL." not in out
    assert "SL." not in out


def test_redact_standard_codes_mixed_k_and_digit_list():
    text = "Gather data on SL.1.1a, SL.K.1b, and SL.1.4 using the checklist."
    out = redact_standard_codes(text)
    assert "SL." not in out
    assert out == "Gather data on using the checklist."


def test_redact_standard_codes_no_op_when_nothing_to_redact():
    """Regression: the cleanup passes used to run unconditionally, so
    code-free text lost real words ("with and without" -> "with without")
    and trailing punctuation even when no code was present."""
    assert (
        redact_standard_codes("Compare texts with and without illustrations.")
        == "Compare texts with and without illustrations."
    )
    assert (
        redact_standard_codes("Sort the words using and matching picture cards.")
        == "Sort the words using and matching picture cards."
    )
    assert redact_standard_codes("Finish the sentence,") == "Finish the sentence,"


def test_redact_standard_codes_preserves_non_ccss_dotted_references():
    """Regression: the code regex over-matched outline/section references
    that merely look like CCSS codes (LETTERS.digits.digits), silently
    deleting legitimate text like 'section A.1.2' or roman-numeral outlines."""
    assert (
        redact_standard_codes("Turn to section A.1.2 of the workbook.")
        == "Turn to section A.1.2 of the workbook."
    )
    assert (
        redact_standard_codes("See outline II.3.4 for details.")
        == "See outline II.3.4 for details."
    )
    # A real code alongside a section reference: only the real code goes.
    out = redact_standard_codes("See section A.1.2 and RL.K.1 for details.")
    assert "A.1.2" in out
    assert "RL." not in out


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
                    location="Work Time A",
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
                    location="Work Time A",
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


def test_sanitize_fills_written_production_from_whiteboard_step():
    """Enterprise guard: optional whiteboard write/draw must not stay NONE OBSERVED."""
    step = (
        "Before reading, provide white boards and dry-erase markers as an option "
        "for students to record (in drawing or writing) their ideas."
    )
    lesson = _lesson_with_steps(
        steps=[
            "'What does the sun look like?'",
            step,
        ]
    )
    norm = minimal_normalized_lesson(resource_id="G1M2U2L3").model_copy(
        update={
            "student_actions": StudentActions(
                oral_production="Answer questions about the sun.",
                written_production="NONE OBSERVED",
            ),
            "subject_profile": SubjectProfile(mode="interpretation", genre="n/a"),
            "evidence": [
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
    assert fixed.student_actions.written_production != "NONE OBSERVED"
    assert any(
        "written_production" in (e.supports_action or []) for e in fixed.evidence
    )
    assert fixed.subject_profile.mode == "both"
    assert any("written_production" in w for w in warnings)


def test_written_production_evidence_redacts_standard_codes():
    """ensure_written_production must not re-introduce CCSS codes after redaction."""
    step = (
        "Invite students to write their answer on SL.1.1a, SL.1.1b, and SL.1.4 "
        "using the checklist."
    )
    lesson = _lesson_with_steps(
        steps=["'What does the sun look like?'", step],
    )
    norm = minimal_normalized_lesson(resource_id="G1M2U2L3").model_copy(
        update={
            "student_actions": StudentActions(
                oral_production="Answer questions about the sun.",
                written_production="NONE OBSERVED",
            ),
            "subject_profile": SubjectProfile(mode="interpretation", genre="n/a"),
            "evidence": [
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
    fixed, _warnings = sanitize_normalized_lesson(norm, lesson)
    assert fixed.student_actions.written_production != "NONE OBSERVED"
    for ev in fixed.evidence:
        assert "SL." not in ev.quote
    assert any("written_production" in (e.supports_action or []) for e in fixed.evidence)


def test_location_with_comma_rest_does_not_insert_space_before_punctuation():
    from veramynd_parser.normalize.sanitize import canonicalize_evidence_locations

    lesson = _lesson_with_steps()
    norm_evidence = [
        EvidenceItem(
            quote="'What does the sun look like?'",
            location="Work Time A, page 5",
            actor="student",
            evidence_role="elicitation_check",
            support="with_prompting",
            supports_action=["oral_production"],
        )
    ]
    fixed, warnings = canonicalize_evidence_locations(norm_evidence, lesson)
    assert fixed[0].location == "Work Time A, page 5"
    assert not any(" , " in w for w in warnings)


def test_canonicalize_rejects_unjoinable_location():
    from veramynd_parser.normalize.sanitize import canonicalize_evidence_locations

    lesson = _lesson_with_steps()
    bad = [
        EvidenceItem(
            quote="'What does the sun look like?'",
            location="Made Up Section Z",
            actor="student",
            evidence_role="elicitation_check",
            support="with_prompting",
            supports_action=["oral_production"],
        )
    ]
    with pytest.raises(ValueError, match="does not join"):
        canonicalize_evidence_locations(bad, lesson)


def test_sanitize_ignores_next_lesson_write_mentions():
    lesson = _lesson_with_steps(
        steps=[
            "'What does the sun look like?'",
            "Tell students that in the next lesson they will write and draw about key details.",
        ]
    )
    norm = minimal_normalized_lesson(resource_id="G1M2U2L3").model_copy(
        update={
            "student_actions": StudentActions(
                oral_production="Answer questions about the sun.",
                written_production="NONE OBSERVED",
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
            ],
        }
    )
    fixed, _warnings = sanitize_normalized_lesson(norm, lesson)
    assert fixed.student_actions.written_production == "NONE OBSERVED"


def test_sanitize_ignores_draw_from_language_idiom():
    lesson = _lesson_with_steps(
        steps=[
            "'What does the sun look like?'",
            "Invite students to draw from this language as they complete their culminating tasks.",
        ]
    )
    norm = minimal_normalized_lesson(resource_id="G1M2U2L3").model_copy(
        update={
            "student_actions": StudentActions(
                oral_production="Answer questions about the sun.",
                written_production="NONE OBSERVED",
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
            ],
        }
    )
    fixed, _warnings = sanitize_normalized_lesson(norm, lesson)
    assert fixed.student_actions.written_production == "NONE OBSERVED"


def test_scrub_phonics_omission_when_sound_out_in_steps():
    """Production: MSN/feedback encoding must not sit under what_is_NOT_taught."""
    lesson = _lesson_with_steps(
        steps=[
            "'What does the sun look like?'",
            (
                "Emphasize process and effort in writing by modeling how to sound "
                "out a word with tricky spelling."
            ),
        ]
    )
    norm = minimal_normalized_lesson(resource_id="G1M2U1L8").model_copy(
        update={
            "what_is_NOT_taught": ["phonics/decoding", "Fluency"],
            "evidence": [
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
    assert "phonics/decoding" not in fixed.what_is_NOT_taught
    assert "Fluency" in fixed.what_is_NOT_taught
    assert any("phonics/decoding" in w for w in warnings)


def test_scrub_phonics_omission_when_stretch_and_spell_feedback():
    lesson = _lesson_with_steps(
        steps=[
            (
                "Offer students specific feedback. (Example: 'I saw that Elijah "
                "not only drew the character under the section for characters, "
                "but he also stretched and spelled the word boy under his drawing.')"
            ),
        ]
    )
    norm = minimal_normalized_lesson(resource_id="G1M2U1L3").model_copy(
        update={
            "what_is_NOT_taught": ["Phonics/decoding"],
            "evidence": [
                EvidenceItem(
                    quote=(
                        "Offer students specific feedback. (Example: 'I saw that Elijah "
                        "not only drew the character under the section for characters, "
                        "but he also stretched and spelled the word boy under his drawing.')"
                    ),
                    location="Work Time A",
                    actor="student",
                    evidence_role="student_production",
                    support="independent",
                    supports_action=["written_production"],
                ),
            ],
        }
    )
    fixed, warnings = sanitize_normalized_lesson(norm, lesson)
    assert fixed.what_is_NOT_taught == []
    assert any("Phonics/decoding" in w for w in warnings)


def test_keeps_phonics_omission_when_no_encoding_evidence():
    lesson = _lesson_with_steps(
        steps=["Invite students to turn and talk about the moon."]
    )
    norm = minimal_normalized_lesson(resource_id="G1M2U1L1").model_copy(
        update={
            "what_is_NOT_taught": ["phonics/decoding", "Fluency"],
            "evidence": [
                EvidenceItem(
                    quote="Invite students to turn and talk about the moon.",
                    location="Work Time A",
                    actor="student",
                    evidence_role="directive_prompt",
                    support="with_prompting",
                    supports_action=["oral_production"],
                ),
            ],
        }
    )
    fixed, warnings = sanitize_normalized_lesson(norm, lesson)
    assert "phonics/decoding" in fixed.what_is_NOT_taught
    assert not any("phonics" in w.lower() for w in warnings)


def test_resolve_quote_recovers_source_line_not_llm_rewrite():
    """LLM single-quote / truncated rewrites must snap back to Stage-1 text."""
    from veramynd_parser.normalize.sanitize import resolve_verbatim_quote

    source = 'Ask: "What does this sentence mean?" Responses will vary.'
    lesson = _lesson_with_steps(steps=[source, "Invite students to turn and talk."])
    lines = [source, "Invite students to turn and talk."]
    corpus = "\n".join(lines)
    llm_quote = "Ask: 'What does this sentence mean?' Responses will vary."
    resolved = resolve_verbatim_quote(llm_quote, lines, corpus)
    assert resolved == source

    fixed, warnings = sanitize_normalized_lesson(
        minimal_normalized_lesson(resource_id="G1M2U2L5").model_copy(
            update={
                "evidence": [
                    EvidenceItem(
                        quote=llm_quote,
                        location="Work Time A",
                        actor="student",
                        evidence_role="elicitation_check",
                        support="with_prompting",
                        supports_action=["oral_production"],
                    ),
                ],
            }
        ),
        lesson,
    )
    assert fixed.evidence[0].quote == source
    assert any("verbatim" in w for w in warnings)


def test_resolve_quote_recovers_line_after_standard_code_redaction():
    from veramynd_parser.normalize.sanitize import resolve_verbatim_quote

    source = (
        "Circulate to observe students as they discuss. Gather data on "
        "SL.1.1a, SL.1.1b, SL.1.4, and SL.1.6 using the Speaking and Listening Checklist."
    )
    llm_quote = (
        "Circulate to observe students as they discuss. Gather data on using "
        "the Speaking and Listening Checklist."
    )
    resolved = resolve_verbatim_quote(llm_quote, [source], source)
    assert resolved == source


def test_resolve_verbatim_quote_reverse_containment_prefers_the_full_line():
    """Regression: reverse-containment (a short source line that's a PREFIX of
    the LLM's longer quote) used to return on the first hit, so an early short
    line beat a later, more complete/exact line for the same quote."""
    lines = [
        "Direct students to reread the text",
        "Direct students to reread the text and underline the words that rhyme.",
    ]
    corpus = "\n".join(lines)
    quote = "Direct students to reread the text and underline the words that rhyme."
    resolved = resolve_verbatim_quote(quote, lines, corpus)
    assert resolved == lines[1]


def test_sanitize_evidence_prefers_quote_from_its_own_claimed_block():
    """Regression: containment resolution picked the globally shortest
    matching line with no regard for which block the evidence claims —
    a short line from Opening could beat the actual step in Work Time."""
    from veramynd_parser.models import AgendaItem

    lesson = Lesson(
        code="G1M2U2L3",
        grade=1,
        module=2,
        unit=2,
        lesson=3,
        title="Lesson",
        page_start=1,
        page_end=2,
        agenda=[
            AgendaItem(
                section="Opening", letter="A",
                title="Invite students to share and discuss", minutes=10,
            ),
            AgendaItem(section="Work Time", letter="A", title="B", minutes=50),
        ],
        instructional_blocks=[
            InstructionalBlock(
                section="Work Time",
                letter="A",
                title="Shared writing",
                page=1,
                steps=["Invite students to share their observations about the moon."],
            )
        ],
    )
    # Shorter than the Work Time step, so the OLD "globally shortest wins"
    # logic would pick this Opening-side line instead of the claimed block.
    assert len("Invite students to share and discuss") < len(
        "Invite students to share their observations about the moon."
    )
    evidence = [
        EvidenceItem(
            quote="invite students to share",
            location="Work Time A",
            actor="student",
            evidence_role="directive_prompt",
            support="with_prompting",
            supports_action=["oral_production"],
        )
    ]
    kept, _warnings = sanitize_evidence_against_source(evidence, lesson)
    assert len(kept) == 1
    # Must resolve to the Work Time step it was claimed from, not the shorter
    # Opening agenda title that also contains the same words.
    assert kept[0].quote == "Invite students to share their observations about the moon."


def test_resolve_verbatim_quote_block_preference_is_first_wins_on_duplicate_lines():
    """Regression: the block-preference lookup was dict(zip(source_lines,
    blocks)) — last-wins on a duplicate line. If the same line text appears
    in two different blocks, its FIRST occurrence's block must win the
    lookup — a last-wins mapping makes the duplicate text unmatchable against
    its true (first) block, silently falling back to the globally shortest
    candidate from an unrelated block instead."""
    long_line = "Turn and talk to a partner about your observations."
    short_line = "Turn and talk more."
    lines = [long_line, long_line, short_line]  # long_line appears twice
    blocks = ["Opening A", "Work Time A", "Work Time A"]
    corpus = "\n".join(lines)
    resolved = resolve_verbatim_quote(
        "turn and talk",
        lines,
        corpus,
        source_blocks=blocks,
        preferred_block="Opening A",
    )
    # long_line's FIRST occurrence is tagged "Opening A" — first-wins must
    # resolve to it despite short_line being the globally shortest candidate.
    assert resolved == long_line
