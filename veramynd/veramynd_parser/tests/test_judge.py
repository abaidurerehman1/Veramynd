"""Tests for alignment judge grounding + pipeline (mocked LLM)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from veramynd_parser.cli import build_parser
from veramynd_parser.judge.grounding import is_grounded, normalize_for_grounding
from veramynd_parser.judge.io import (
    JudgeIoError,
    lesson_raw_text_from_stage1,
    load_retrieve_candidates,
    load_standard_raw_text,
)
from veramynd_parser.judge.models import (
    ClauseClientDraft,
    ClauseJudgment,
    JudgeClientBatchDraft,
    JudgeClientDraft,
    JudgeLlmDraft,
)
from veramynd_parser.judge.pipeline import DEFAULT_BATCH_MAX_TOKENS, judge_pair, judge_retrieve_file


def test_grounding_finds_quote_with_quote_normalization():
    lesson = 'Students ask: “Who is the boy?” using key details.'
    evidence = "Students ask: \"Who is the boy?\" using key details."
    assert is_grounded(evidence, lesson)
    assert "who is the boy" in normalize_for_grounding(lesson)


def test_grounding_rejects_fabricated_quote():
    lesson = "Students identify the setting of the story."
    assert not is_grounded(
        "Students conduct multi-source research projects independently.",
        lesson,
    )


def test_grounding_empty_evidence_ok_only_when_allowed():
    assert is_grounded("", "any lesson text", allow_empty=True)
    assert not is_grounded("", "any lesson text", allow_empty=False)


def test_grounding_rejects_empty_positive_claim():
    assert not is_grounded("", "Students identify the setting.", allow_empty=False)


def test_grounding_requires_all_ellipsis_segments():
    lesson = (
        "Invite students to turn and talk to an elbow partner: "
        "'Who is the main character?' (the boy) "
        "'Where does the story take place?' (a farm)"
    )
    good = (
        "Invite students to turn and talk to an elbow partner: "
        "'Who is the main character?' (the boy) ... "
        "'Where does the story take place?' (a farm)"
    )
    assert is_grounded(good, lesson)
    bad = (
        "Invite students to turn and talk to an elbow partner: "
        "'Who is the main character?' (the boy) ... "
        "Students invent research across multiple digital sources today."
    )
    assert not is_grounded(bad, lesson)


def test_grounding_accepts_semicolon_joined_noncontiguous_quotes():
    """P8: real quotes joined with ';' must ground independently."""
    lesson = (
        "Invite students to turn and talk with an elbow partner: "
        '"What does the author tell us about Papa?" '
        "Later, students present aloud using a clear speaking voice. "
        "Then they complete the response sheet about the story."
    )
    evidence = (
        'Invite students to turn and talk with an elbow partner: '
        '"What does the author tell us about Papa?"; '
        "students present aloud using a clear speaking voice"
    )
    assert is_grounded(evidence, lesson)


def test_grounding_rejects_semicolon_join_when_one_quote_is_fabricated():
    lesson = (
        "Invite students to turn and talk with an elbow partner about Papa. "
        "Students complete the response sheet about the story."
    )
    evidence = (
        "Invite students to turn and talk with an elbow partner about Papa; "
        "Students invent multi-source research projects independently today."
    )
    assert not is_grounded(evidence, lesson)


def test_grounding_keeps_contiguous_text_that_contains_semicolon():
    lesson = (
        "Teacher says: Listen carefully; then answer with a partner "
        "using evidence from the text."
    )
    evidence = (
        "Teacher says: Listen carefully; then answer with a partner "
        "using evidence from the text."
    )
    assert is_grounded(evidence, lesson)


def test_grounding_accepts_internal_ellipsis_when_span_is_present():
    """P8: '...' inside one real quote is not a failed multi-stitch."""
    lesson = (
        "Why did Moon change its mind? What was the central message "
        "or lesson that Moon learned? (Moon realized that the world "
        "is beautiful no matter if it's day or night.)"
    )
    evidence = (
        "'Why did Moon change its mind? What was the central message "
        "or lesson that Moon learned?' (Moon realized that the world "
        "is beautiful no matter if it's day or night...)"
    )
    assert is_grounded(evidence, lesson)


def test_p10_scrubs_editorial_brackets_and_recovers_verbatim():
    from veramynd_parser.judge.grounding import (
        first_grounded_evidence,
        scrub_editorial_brackets,
    )

    lesson = "Cold call a few selected students to share out."
    dirty = (
        "Cold call a few selected students to share out "
        "[their ideas about the central message]."
    )
    assert scrub_editorial_brackets(dirty) == (
        "Cold call a few selected students to share out."
    )
    chosen = first_grounded_evidence(dirty, lesson_raw_text=lesson)
    assert chosen == "Cold call a few selected students to share out."
    assert is_grounded(chosen, lesson)


def test_p10_recovers_prefix_when_bracket_gloss_corrupts_tail():
    from veramynd_parser.judge.grounding import first_grounded_evidence

    lesson = (
        "Invite students to complete Part I of the Unit 1 Assessment "
        "response sheet. Remind them to use evidence."
    )
    dirty = (
        "Invite students to complete Part I of the Unit 1 Assessment "
        "response sheet. [writing about character and setting after "
        "listening to the text]"
    )
    chosen = first_grounded_evidence(dirty, lesson_raw_text=lesson)
    assert chosen is not None
    assert "Part I of the Unit 1 Assessment response sheet" in chosen
    assert "[" not in chosen
    assert is_grounded(chosen, lesson)


def test_p10_still_rejects_pure_paraphrase():
    from veramynd_parser.judge.grounding import first_grounded_evidence

    lesson = "Students identify the setting of the story."
    dirty = (
        "Students [independently] invent multi-source research projects "
        "across several digital databases today."
    )
    assert first_grounded_evidence(dirty, lesson_raw_text=lesson) is None


def test_judge_pair_keeps_llm_status_and_clauses_when_grounded():
    lesson = "Students identify the setting of the story."

    def fake_complete(**kwargs):
        return JudgeLlmDraft(
            matched_status="partial",
            clauses=[
                ClauseJudgment(clause="identify setting", met=True, note=""),
                ClauseJudgment(clause="identify characters", met=False, note=""),
            ],
            evidence=lesson,
            evidence_page=1,
            confidence="high",
            rationale="Setting is practiced; characters are not.",
        )

    v = judge_pair(
        resource_id="G1M2U1L3",
        lesson_raw_text=lesson,
        standard={
            "standard_code": "1.T.T.1.a",
            "raw_text": "Identify characters and setting.",
        },
        use_cache=False,
        escalate=False,
        complete_fn=fake_complete,
    )
    assert v.matched_status == "partial"
    assert v.grounded
    assert [c.met for c in v.clauses] == [True, False]
    assert v.input_scope_caveat == ""


def test_judge_pair_rejects_empty_evidence_full():
    def fake_complete(**kwargs):
        return JudgeLlmDraft(
            matched_status="full",
            clauses=[ClauseJudgment(clause="identify setting", met=True, note="")],
            evidence="",
            evidence_page=1,
            confidence="high",
            rationale="No quote.",
        )

    v = judge_pair(
        resource_id="G1M2U1L3",
        lesson_raw_text="Students identify the setting of the story.",
        standard={
            "standard_code": "1.T.T.1.a",
            "raw_text": "Identify characters and setting.",
        },
        use_cache=False,
        complete_fn=fake_complete,
    )
    assert v.matched_status == "none"
    assert v.grounded is False
    assert "REJECTED" in v.rationale
    assert v.needs_review is True
    assert "grounding rejection" in v.review_reason
    assert v.confidence == "low"


def test_p2_needs_review_on_low_confidence_even_when_grounded():
    lesson = "Students identify the setting of the story."

    def fake_complete(**kwargs):
        return JudgeLlmDraft(
            matched_status="partial",
            clauses=[
                ClauseJudgment(clause="identify setting", met=True, note=""),
                ClauseJudgment(clause="identify characters", met=False, note=""),
            ],
            evidence=lesson,
            evidence_page=1,
            confidence="low",
            rationale="Setting only.",
            needs_review=False,
            review_reason="",
        )

    v = judge_pair(
        resource_id="G1M2U1L3",
        lesson_raw_text=lesson,
        standard={
            "standard_code": "1.T.T.1.a",
            "raw_text": "Identify characters and setting.",
        },
        use_cache=False,
        escalate=False,
        complete_fn=fake_complete,
    )
    assert v.grounded is True
    assert v.needs_review is True
    assert "confidence=low" in v.review_reason


def test_p2_needs_review_on_list_waffle_rationale():
    lesson = (
        "Invite students to turn and talk with an elbow partner: "
        "What does the author tell us about Papa?"
    )

    def fake_complete(**kwargs):
        return JudgeLlmDraft(
            matched_status="partial",
            clauses=[
                ClauseJudgment(clause="work with others", met=True, note=""),
                ClauseJudgment(clause="discuss topics", met=True, note=""),
            ],
            evidence=lesson,
            evidence_page=1,
            confidence="high",
            rationale=(
                "This is an OR-like list of collaborative purposes under one "
                "work-with-others umbrella, but each names a distinct "
                "collaborative act, so score Partial."
            ),
            needs_review=False,
            review_reason="",
        )

    v = judge_pair(
        resource_id="G1M2U1L8",
        lesson_raw_text=lesson,
        standard={
            "standard_code": "1.P.CP.1.d",
            "raw_text": (
                "Work with others to discuss topics, investigate questions, "
                "solve problems, and explore and create texts."
            ),
        },
        use_cache=False,
        escalate=False,
        complete_fn=fake_complete,
    )
    assert v.matched_status == "partial"
    assert v.needs_review is True
    assert "list-standard waffle" in v.review_reason
    assert v.confidence == "low"


def test_escalate_changes_cache_key():
    from veramynd_parser.normalize.cache import ContentAddressedCache
    from veramynd_parser.judge.pipeline import PROMPT_VERSION

    k0 = ContentAddressedCache.key(
        PROMPT_VERSION, "openai", "gpt-4.1", "escalate=0", "", "sys", "{}"
    )
    k1 = ContentAddressedCache.key(
        PROMPT_VERSION, "openai", "gpt-4.1", "escalate=1", "gpt-5", "sys", "{}"
    )
    assert k0 != k1


def test_should_escalate_enterprise_triggers():
    from veramynd_parser.judge.pipeline import _should_escalate

    clause = ClauseJudgment(clause="c", met=True, note="")

    assert _should_escalate(
        JudgeLlmDraft(
            matched_status="partial",
            clauses=[clause],
            evidence="x",
            evidence_page=1,
            confidence="high",
            rationale="r",
        )
    )
    assert _should_escalate(
        JudgeLlmDraft(
            matched_status="full",
            clauses=[clause],
            evidence="x",
            evidence_page=1,
            confidence="medium",
            rationale="r",
        )
    )
    assert _should_escalate(
        JudgeLlmDraft(
            matched_status="full",
            clauses=[clause],
            evidence="",
            evidence_page=1,
            confidence="high",
            rationale="r",
        )
    )
    assert not _should_escalate(
        JudgeLlmDraft(
            matched_status="full",
            clauses=[clause],
            evidence="grounded quote",
            evidence_page=1,
            confidence="high",
            rationale="r",
        )
    )
    assert not _should_escalate(
        JudgeLlmDraft(
            matched_status="none",
            clauses=[ClauseJudgment(clause="c", met=False, note="")],
            evidence="",
            evidence_page=1,
            confidence="high",
            rationale="r",
        )
    )
    assert _should_escalate(
        JudgeLlmDraft(
            matched_status="full",
            clauses=[
                ClauseJudgment(clause="a", met=True, note=""),
                ClauseJudgment(clause="b", met=False, note=""),
            ],
            evidence="grounded quote",
            evidence_page=1,
            confidence="high",
            rationale="r",
        )
    )
    assert _should_escalate(
        JudgeLlmDraft(
            matched_status="full",
            clauses=[clause],
            evidence="grounded quote",
            evidence_page=1,
            confidence="high",
            rationale="r",
            needs_review=True,
            review_reason="partial-or-full",
        )
    )


def test_judge_lesson_batch_escalates_in_one_call(monkeypatch):
    """Borderline codes go to one Opus batch, not N pair calls."""
    from veramynd_parser.judge import pipeline as jp
    from veramynd_parser.judge.models import JudgeBatchDraft, JudgeBatchItem

    lesson = "Students identify the setting of the story on page 1."
    standards = [
        {"standard_code": "1.T.T.1.a", "raw_text": "Identify setting."},
        {"standard_code": "1.T.T.1.b", "raw_text": "Identify characters."},
        {"standard_code": "1.T.RA.1", "raw_text": "Conduct research."},
    ]
    calls: list[tuple[str, list[str]]] = []

    def fake_batch(**kwargs):
        model = kwargs["model"]
        user = kwargs["user"]
        if model == "claude-sonnet-4-5":
            calls.append(("sonnet", ["1.T.T.1.a", "1.T.T.1.b", "1.T.RA.1"]))
            return JudgeBatchDraft(
                results=[
                    JudgeBatchItem(
                        standard_code="1.T.T.1.a",
                        matched_status="partial",
                        clauses=[
                            ClauseJudgment(clause="setting", met=True, note="")
                        ],
                        evidence=lesson,
                        evidence_page=1,
                        confidence="medium",
                        rationale="partial setting",
                    ),
                    JudgeBatchItem(
                        standard_code="1.T.T.1.b",
                        matched_status="partial",
                        clauses=[
                            ClauseJudgment(clause="characters", met=False, note="")
                        ],
                        evidence="",
                        evidence_page=None,
                        confidence="low",
                        rationale="unclear",
                        needs_review=True,
                        review_reason="low confidence",
                    ),
                    JudgeBatchItem(
                        standard_code="1.T.RA.1",
                        matched_status="none",
                        clauses=[
                            ClauseJudgment(clause="research", met=False, note="")
                        ],
                        evidence="",
                        evidence_page=None,
                        confidence="high",
                        rationale="no research",
                    ),
                ]
            )
        assert model == "claude-opus-4-6"
        # Escalate batch should only include the two borderline codes.
        assert '"standard_code": "1.T.T.1.a"' in user
        assert '"standard_code": "1.T.T.1.b"' in user
        assert '"standard_code": "1.T.RA.1"' not in user
        calls.append(("opus", ["1.T.T.1.a", "1.T.T.1.b"]))
        return JudgeBatchDraft(
            results=[
                JudgeBatchItem(
                    standard_code="1.T.T.1.a",
                    matched_status="full",
                    clauses=[
                        ClauseJudgment(clause="setting", met=True, note="")
                    ],
                    evidence=lesson,
                    evidence_page=1,
                    confidence="high",
                    rationale="full after escalate",
                ),
                JudgeBatchItem(
                    standard_code="1.T.T.1.b",
                    matched_status="none",
                    clauses=[
                        ClauseJudgment(clause="characters", met=False, note="")
                    ],
                    evidence="",
                    evidence_page=None,
                    confidence="high",
                    rationale="still none",
                ),
            ]
        )

    monkeypatch.setattr(jp, "_call_judge_batch", fake_batch)
    pair_calls = {"n": 0}

    def boom_pair(**kwargs):
        pair_calls["n"] += 1
        raise AssertionError("pair escalate should not run when batch succeeds")

    monkeypatch.setattr(jp, "judge_pair", boom_pair)

    verdicts = jp.judge_lesson_batch(
        resource_id="G1M2U1L1",
        lesson_raw_text=lesson,
        standards=standards,
        model="claude-sonnet-4-5",
        escalate_model="claude-opus-4-6",
        escalate=True,
        use_cache=False,
        complete_fn=None,
    )
    assert [c[0] for c in calls] == ["sonnet", "opus"]
    assert calls[1][1] == ["1.T.T.1.a", "1.T.T.1.b"]
    assert pair_calls["n"] == 0
    by = {v.standard_code: v for v in verdicts}
    assert by["1.T.T.1.a"].escalated is True
    assert by["1.T.T.1.a"].judge_model == "claude-opus-4-6"
    assert by["1.T.T.1.a"].matched_status == "full"
    assert by["1.T.T.1.b"].escalated is True
    assert by["1.T.RA.1"].escalated is False
    assert by["1.T.RA.1"].judge_model == "claude-sonnet-4-5"


def test_judge_lesson_batch_escalate_falls_back_to_pair(monkeypatch):
    from veramynd_parser.judge import pipeline as jp
    from veramynd_parser.judge.models import JudgeBatchDraft, JudgeBatchItem, JudgeLlmDraft

    lesson = "Students identify the setting of the story."
    standards = [
        {"standard_code": "1.T.T.1.a", "raw_text": "Identify setting."},
    ]
    batch_n = {"n": 0}

    def fake_batch(**kwargs):
        batch_n["n"] += 1
        if kwargs["model"] == "claude-opus-4-6":
            raise jp.JudgeError("opus batch boom")
        return JudgeBatchDraft(
            results=[
                JudgeBatchItem(
                    standard_code="1.T.T.1.a",
                    matched_status="partial",
                    clauses=[ClauseJudgment(clause="setting", met=True, note="")],
                    evidence=lesson,
                    evidence_page=1,
                    confidence="medium",
                    rationale="borderline",
                )
            ]
        )

    def fake_pair(**kwargs):
        return JudgeLlmDraft(
            matched_status="full",
            clauses=[ClauseJudgment(clause="setting", met=True, note="")],
            evidence=lesson,
            evidence_page=1,
            confidence="high",
            rationale="pair escalate ok",
        )

    monkeypatch.setattr(jp, "_call_judge_batch", fake_batch)
    monkeypatch.setattr(
        jp,
        "judge_pair",
        lambda **kwargs: jp._finalize_verdict(
            resource_id=kwargs["resource_id"],
            standard_code=kwargs["standard"]["standard_code"],
            standard_raw_text=kwargs["standard"]["raw_text"],
            lesson_raw_text=kwargs["lesson_raw_text"],
            draft=fake_pair(**kwargs),
            used_model=kwargs["model"],
            escalated=False,
            retrieval=kwargs.get("retrieval"),
            prompt_version=jp.PROMPT_VERSION,
        ),
    )

    verdicts = jp.judge_lesson_batch(
        resource_id="G1M2U1L1",
        lesson_raw_text=lesson,
        standards=standards,
        model="claude-sonnet-4-5",
        escalate_model="claude-opus-4-6",
        escalate=True,
        use_cache=False,
    )
    assert batch_n["n"] == 2  # sonnet + failed opus
    assert len(verdicts) == 1
    assert verdicts[0].escalated is True
    assert verdicts[0].matched_status == "full"
    assert verdicts[0].judge_model == "claude-opus-4-6"


def test_lesson_raw_text_joins_steps():
    lesson = {
        "title": "Lesson 3",
        "learning_targets": [{"text": "I can ask questions."}],
        "instructional_blocks": [
            {
                "section": "Work Time",
                "letter": "B",
                "title": "Close Read",
                "page": 70,
                "steps": [
                    "Invite students to ask and answer questions about the boy.",
                    "Students write about the setting.",
                ],
            }
        ],
    }
    text = lesson_raw_text_from_stage1(lesson)
    assert "Close Read" in text
    assert "ask and answer questions" in text
    assert "page 70" in text


def test_page_from_evidence_uses_block_page_not_location():
    from veramynd_parser.judge.grounding import page_from_evidence

    lesson = {
        "title": "Lesson 1",
        "instructional_blocks": [
            {
                "section": "Opening",
                "letter": "B",
                "title": "Picture Tea Party",
                "page": 45,
                "steps": ["Share using the frame In my picture, I see the sun."],
            },
            {
                "section": "Work Time",
                "letter": "B",
                "title": "Back-to-Back",
                "page": 48,
                "steps": [
                    "Guide students: I noticed that the sun is bright today."
                ],
            },
        ],
    }
    text = lesson_raw_text_from_stage1(lesson)
    assert page_from_evidence("I noticed that the sun is bright today.", text) == 48
    assert page_from_evidence("In my picture, I see the sun.", text) == 45
    assert page_from_evidence("", text) is None


def test_judge_pair_fills_evidence_page_from_lesson_blocks():
    lesson = {
        "title": "Lesson 1",
        "instructional_blocks": [
            {
                "section": "Work Time",
                "letter": "C",
                "title": "Independent Writing",
                "page": 49,
                "steps": [
                    "Invite students to use the response sheet to capture "
                    "the things they noticed and wondered about the sun."
                ],
            }
        ],
    }
    text = lesson_raw_text_from_stage1(lesson)
    quote = (
        "Invite students to use the response sheet to capture "
        "the things they noticed and wondered about the sun."
    )

    def fake_complete(**kwargs):
        return JudgeLlmDraft(
            matched_status="full",
            clauses=[
                ClauseJudgment(clause="generate ideas", met=True, note=""),
            ],
            evidence=quote,
            evidence_page=None,
            confidence="high",
            rationale="Students generate ideas on the response sheet.",
        )

    v = judge_pair(
        resource_id="G1M2U1L1",
        lesson_raw_text=text,
        standard={
            "standard_code": "1.P.EICC.4.c",
            "raw_text": "Generate ideas for content.",
        },
        use_cache=False,
        complete_fn=fake_complete,
    )
    assert v.matched_status == "full"
    assert v.evidence_page == 49


def test_judge_pair_full_when_grounded(tmp_path: Path):
    lesson = (
        "Invite students to ask and answer questions about the boy and the sun "
        "using key details from the text."
    )
    quote = (
        "Invite students to ask and answer questions about the boy and the sun "
        "using key details from the text."
    )

    def fake_complete(**kwargs):
        return JudgeLlmDraft(
            matched_status="full",
            clauses=[
                ClauseJudgment(clause="ask questions about key details", met=True, note=""),
                ClauseJudgment(clause="answer questions about key details", met=True, note=""),
            ],
            evidence=quote,
            evidence_page=70,
            confidence="high",
            rationale="Students ask and answer with key details.",
        )

    v = judge_pair(
        resource_id="G1M2U1L3",
        lesson_raw_text=lesson,
        standard={
            "standard_code": "1.T.T.1.a",
            "raw_text": "Identify characters and setting.",
            "competency_statement": "Identify story elements.",
            "domain_primary": "Comprehension",
        },
        use_cache=False,
        complete_fn=fake_complete,
    )
    assert v.matched_status == "full"
    assert v.grounded is True
    assert v.standard_code == "1.T.T.1.a"


def test_judge_pair_rejects_ungrounded_full():
    def fake_complete(**kwargs):
        return JudgeLlmDraft(
            matched_status="full",
            clauses=[ClauseJudgment(clause="research", met=True, note="")],
            evidence="Students invent a quote that is not in the lesson at all.",
            evidence_page=1,
            confidence="high",
            rationale="Fabricated.",
        )

    v = judge_pair(
        resource_id="G1M2U1L3",
        lesson_raw_text="Students identify the setting.",
        standard={
            "standard_code": "1.T.RA.1",
            "raw_text": "Conduct research using multiple sources.",
        },
        use_cache=False,
        complete_fn=fake_complete,
    )
    assert v.matched_status == "none"
    assert v.grounded is False
    assert "REJECTED" in v.rationale


def test_judge_pair_uses_grounded_piece_of_stitched_quote():
    lesson = (
        "Guide students through the protocol using the sentence frame: "
        "I noticed that the sun __________. Then they share."
    )
    stitched = (
        "In my picture, I see_______. / I noticed that the sun __________. / "
        "One thing I wonder about the moon/stars is ____________."
    )

    def fake_complete(**kwargs):
        return JudgeLlmDraft(
            matched_status="full",
            clauses=[ClauseJudgment(clause="present ideas clearly", met=True, note="")],
            evidence=stitched,
            evidence_page=None,
            confidence="high",
            rationale="Students present observations aloud.",
            evidence_candidates=[stitched],
        )

    v = judge_pair(
        resource_id="G1M2U1L1",
        lesson_raw_text=lesson,
        standard={
            "standard_code": "1.P.CP.2.a",
            "raw_text": "Communicate clearly to present ideas.",
        },
        use_cache=False,
        complete_fn=fake_complete,
    )
    assert v.matched_status == "full"
    assert v.grounded is True
    assert v.evidence == "I noticed that the sun __________."
    assert "REJECTED" not in v.rationale


def test_judge_pair_uses_later_student_quote_when_first_not_in_lesson():
    good = "Invite students to use the response sheet to capture notices."
    lesson = f"Work Time C. {good} Students write and draw."

    def fake_complete(**kwargs):
        return JudgeClientDraft(
            candidate_id="G1M2U1L1",
            location="Work Time C",
            standard_code="1.P.EICC.4.c",
            clauses=[
                ClauseClientDraft(
                    clause="prior knowledge",
                    judgment="met",
                    actor="student",
                    student_quote="This fabricated quote is not in the lesson text.",
                    teacher_quote="",
                    why="wrong quote",
                ),
                ClauseClientDraft(
                    clause="from texts",
                    judgment="met",
                    actor="student",
                    student_quote=good,
                    teacher_quote="",
                    why="response sheet",
                ),
            ],
            alignment="full",
            needs_review=False,
            review_reason="",
            evidence="Prose write-up that is not a lesson quote.",
            anchor_note="",
        )

    v = judge_pair(
        resource_id="G1M2U1L1",
        lesson_raw_text=lesson,
        standard={
            "standard_code": "1.P.EICC.4.c",
            "raw_text": "Generate ideas for content.",
        },
        use_cache=False,
        complete_fn=fake_complete,
    )
    assert v.matched_status == "full"
    assert v.grounded is True
    assert v.evidence == good


def test_judge_retrieve_file_mocked(tmp_path: Path):
    lesson_path = tmp_path / "G1M2U1L3.json"
    lesson_path.write_text(
        json.dumps(
            {
                "code": "G1M2U1L3",
                "title": "Lesson 3",
                "instructional_blocks": [
                    {
                        "section": "Work Time",
                        "letter": "B",
                        "title": "Close Read",
                        "page": 70,
                        "steps": [
                            "Students identify characters and the setting in the story."
                        ],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    retrieve_path = tmp_path / "retrieve.json"
    retrieve_path.write_text(
        json.dumps(
            {
                "schema_version": "1.0-retrieve-hybrid",
                "candidates": [
                    {
                        "standard_code": "1.T.T.1.a",
                        "rrf_score": 0.03,
                        "rerank_score": 0.9,
                        "dense_rank": 1,
                        "bm25_rank": 1,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    std_dir = tmp_path / "normalize_standards"
    std_dir.mkdir()
    (std_dir / "1.T.T.1.a.json").write_text(
        json.dumps(
            {
                "standard_code": "1.T.T.1.a",
                "raw_text": "Identify characters, setting, major events, and dialogue.",
                "competency_statement": "Identify story elements.",
                "domain": {"primary": "Comprehension"},
            }
        ),
        encoding="utf-8",
    )

    quote = "Students identify characters and the setting in the story."

    def fake_complete(**kwargs):
        return JudgeLlmDraft(
            matched_status="full",
            clauses=[ClauseJudgment(clause="identify characters/setting", met=True, note="")],
            evidence=quote,
            evidence_page=70,
            confidence="high",
            rationale="Clear match.",
        )

    report = judge_retrieve_file(
        retrieve_file=retrieve_path,
        standards_dir=std_dir,
        lesson_file=lesson_path,
        use_cache=False,
        complete_fn=fake_complete,
    )
    assert report["judged"] == 1
    assert report["judge_mode"] == "pair"
    assert report["by_status"]["full"] == 1
    assert report["verdicts"][0]["grounded"] is True
    assert load_retrieve_candidates(retrieve_path)[0]["standard_code"] == "1.T.T.1.a"


def test_judge_retrieve_file_batch_mocked(tmp_path: Path):
    from veramynd_parser.judge.models import JudgeBatchDraft, JudgeBatchItem

    lesson_path = tmp_path / "G1M2U1L3.json"
    lesson_path.write_text(
        json.dumps(
            {
                "code": "G1M2U1L3",
                "title": "Lesson 3",
                "instructional_blocks": [
                    {
                        "section": "Work Time",
                        "letter": "B",
                        "title": "Close Read",
                        "page": 70,
                        "steps": [
                            "Students identify characters and the setting in the story."
                        ],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    retrieve_path = tmp_path / "retrieve.json"
    retrieve_path.write_text(
        json.dumps(
            {
                "candidates": [
                    {"standard_code": "1.T.T.1.a", "rrf_score": 0.03},
                    {"standard_code": "1.T.RA.1", "rrf_score": 0.02},
                ]
            }
        ),
        encoding="utf-8",
    )
    std_dir = tmp_path / "normalize_standards"
    std_dir.mkdir()
    (std_dir / "1.T.T.1.a.json").write_text(
        json.dumps(
            {
                "standard_code": "1.T.T.1.a",
                "raw_text": "Identify characters and setting.",
            }
        ),
        encoding="utf-8",
    )
    (std_dir / "1.T.RA.1.json").write_text(
        json.dumps(
            {
                "standard_code": "1.T.RA.1",
                "raw_text": "Conduct research using multiple sources.",
            }
        ),
        encoding="utf-8",
    )
    quote = "Students identify characters and the setting in the story."

    def fake_batch(**kwargs):
        return JudgeBatchDraft(
            results=[
                JudgeBatchItem(
                    standard_code="1.T.T.1.a",
                    matched_status="full",
                    clauses=[
                        ClauseJudgment(clause="identify characters/setting", met=True, note="")
                    ],
                    evidence=quote,
                    evidence_page=70,
                    confidence="high",
                    rationale="Match.",
                ),
                JudgeBatchItem(
                    standard_code="1.T.RA.1",
                    matched_status="none",
                    clauses=[ClauseJudgment(clause="research", met=False, note="no research")],
                    evidence="",
                    evidence_page=None,
                    confidence="high",
                    rationale="No research task.",
                ),
            ]
        )

    report = judge_retrieve_file(
        retrieve_file=retrieve_path,
        standards_dir=std_dir,
        lesson_file=lesson_path,
        use_cache=False,
        batch=True,
        batch_complete_fn=fake_batch,
    )
    assert report["judge_mode"] == "batch"
    assert report["judged"] == 2
    assert report["by_status"]["full"] == 1
    assert report["by_status"]["none"] == 1


def test_batch_falls_back_to_pair_on_code_mismatch(tmp_path: Path):
    from veramynd_parser.judge.models import JudgeBatchDraft, JudgeBatchItem

    lesson_path = tmp_path / "G1M2U1L3.json"
    lesson_path.write_text(
        json.dumps(
            {
                "code": "G1M2U1L3",
                "instructional_blocks": [
                    {
                        "section": "Work Time",
                        "letter": "A",
                        "title": "T",
                        "page": 1,
                        "steps": ["Students identify the setting of the story."],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    retrieve_path = tmp_path / "retrieve.json"
    retrieve_path.write_text(
        json.dumps({"candidates": [{"standard_code": "1.T.T.1.a"}]}),
        encoding="utf-8",
    )
    std_dir = tmp_path / "normalize_standards"
    std_dir.mkdir()
    (std_dir / "1.T.T.1.a.json").write_text(
        json.dumps({"standard_code": "1.T.T.1.a", "raw_text": "Identify setting."}),
        encoding="utf-8",
    )

    def bad_batch(**kwargs):
        return JudgeBatchDraft(
            results=[
                JudgeBatchItem(
                    standard_code="WRONG.CODE",
                    matched_status="none",
                    clauses=[ClauseJudgment(clause="x", met=False, note="")],
                    evidence="",
                    evidence_page=None,
                    confidence="low",
                    rationale="bad",
                )
            ]
        )

    calls = {"n": 0}

    def pair_fn(**kwargs):
        calls["n"] += 1
        return JudgeLlmDraft(
            matched_status="none",
            clauses=[ClauseJudgment(clause="identify setting", met=False, note="")],
            evidence="",
            evidence_page=None,
            confidence="high",
            rationale="none",
        )

    report = judge_retrieve_file(
        retrieve_file=retrieve_path,
        standards_dir=std_dir,
        lesson_file=lesson_path,
        use_cache=False,
        batch=True,
        batch_fallback_pair=True,
        batch_complete_fn=bad_batch,
        complete_fn=pair_fn,
    )
    # With both mocks present, use_batch stays True initially; batch fails;
    # fallback uses complete_fn. But wait — if both complete_fn and
    # batch_complete_fn are set, use_batch is True. Fallback then calls
    # judge_pair with complete_fn. Good.
    assert report["judge_mode"] == "pair"
    assert calls["n"] == 1
    assert report["judged"] == 1


def test_judge_aborts_on_billing_without_pair_fallback(tmp_path):
    """Non-retryable OpenAI errors must not fall back to N pair calls."""
    from veramynd_parser.judge.pipeline import JudgeError

    lesson_path = tmp_path / "G1M2U1L1.json"
    lesson_path.write_text(
        json.dumps(
            {
                "code": "G1M2U1L1",
                "instructional_blocks": [
                    {
                        "section": "Work Time",
                        "letter": "A",
                        "title": "T",
                        "page": 1,
                        "steps": ["Students identify characters and the setting in the story."],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    retrieve_path = tmp_path / "retrieve.json"
    retrieve_path.write_text(
        json.dumps(
            {
                "candidates": [
                    {"standard_code": "1.T.T.1.a"},
                    {"standard_code": "1.T.T.2"},
                ]
            }
        ),
        encoding="utf-8",
    )
    std_dir = tmp_path / "normalize_standards"
    std_dir.mkdir()
    for code in ("1.T.T.1.a", "1.T.T.2"):
        (std_dir / f"{code}.json").write_text(
            json.dumps({"standard_code": code, "raw_text": "Identify setting."}),
            encoding="utf-8",
        )

    pair_calls = {"n": 0}

    def billing_batch(**kwargs):
        raise JudgeError(
            "OpenAI account billing is not active (billing_not_active). "
            "Activate billing — this error is not retryable."
        )

    def pair_fn(**kwargs):
        pair_calls["n"] += 1
        return JudgeLlmDraft(
            matched_status="none",
            clauses=[ClauseJudgment(clause="identify setting", met=False, note="")],
            evidence="",
            evidence_page=None,
            confidence="high",
            rationale="none",
        )

    with pytest.raises(JudgeError, match="billing_not_active"):
        judge_retrieve_file(
            retrieve_file=retrieve_path,
            standards_dir=std_dir,
            lesson_file=lesson_path,
            use_cache=False,
            batch=True,
            batch_fallback_pair=True,
            batch_complete_fn=billing_batch,
            complete_fn=pair_fn,
        )
    assert pair_calls["n"] == 0


def test_judge_pair_mode_aborts_on_insufficient_quota(tmp_path):
    from veramynd_parser.judge.pipeline import JudgeError

    lesson_path = tmp_path / "G1M2U1L1.json"
    lesson_path.write_text(
        json.dumps(
            {
                "code": "G1M2U1L1",
                "instructional_blocks": [
                    {
                        "section": "Work Time",
                        "letter": "A",
                        "title": "T",
                        "page": 1,
                        "steps": ["Students identify characters and the setting in the story."],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    retrieve_path = tmp_path / "retrieve.json"
    retrieve_path.write_text(
        json.dumps(
            {
                "candidates": [
                    {"standard_code": "1.T.T.1.a"},
                    {"standard_code": "1.T.T.2"},
                ]
            }
        ),
        encoding="utf-8",
    )
    std_dir = tmp_path / "normalize_standards"
    std_dir.mkdir()
    for code in ("1.T.T.1.a", "1.T.T.2"):
        (std_dir / f"{code}.json").write_text(
            json.dumps({"standard_code": code, "raw_text": "Identify setting."}),
            encoding="utf-8",
        )

    calls = {"n": 0}

    def quota_pair(**kwargs):
        calls["n"] += 1
        raise JudgeError(
            "OpenAI API quota exhausted (insufficient_quota). "
            "Add credits — this error is not retryable."
        )

    with pytest.raises(JudgeError, match="insufficient_quota"):
        judge_retrieve_file(
            retrieve_file=retrieve_path,
            standards_dir=std_dir,
            lesson_file=lesson_path,
            use_cache=False,
            batch=False,
            complete_fn=quota_pair,
        )
    assert calls["n"] == 1


def test_live_prompt_is_client_assembled_not_v1():
    from veramynd_parser.judge.pipeline import (
        BATCH_PROMPT_VERSION,
        PROMPT_VERSION,
        _PROMPT_PATH,
        _load_batch_prompt,
        _load_prompt,
    )

    assert _PROMPT_PATH.name == "assembled_judge_prompt.md"
    assert PROMPT_VERSION == "align_judge.assembled.v1.5"
    assert BATCH_PROMPT_VERSION == "align_judge.assembled.batch.v1.5"
    text = _load_prompt()
    assert "END OF ENGINE" in text
    assert "Georgia K" in text
    assert "ELA Alignment Judge (align_judge.v1.1)" not in text
    batch = _load_batch_prompt()
    assert batch == text
    assert "overrides the single-object Output section" not in batch


def test_ga_overlay_encodes_sme_fences_f1_through_f9():
    """Sheet 3 SME rulings must be present as overlay worked instances."""
    from veramynd_parser.judge.pipeline import _load_prompt

    prompt = _load_prompt()
    assert "1.P.EICC.2.b" in prompt  # F1
    assert "1.L.V.1.b" in prompt  # F2
    assert "1.P.EICC.2.d" in prompt  # F3
    assert "all four" in prompt and "1.T.T.1.a" in prompt  # F4
    assert "(F5 — parenthetical" in prompt
    assert "(F6 — ambient" in prompt
    assert "(F7 — Expository Techniques" in prompt
    assert "1.T.T.1.e" in prompt and "CREATE" in prompt  # F8
    assert "(F9 — collaboration" in prompt
    assert "1.P.CP.1.d" in prompt


def test_client_draft_maps_alignment_and_student_quote():
    quote = "Have students point to the title page."
    draft = JudgeClientDraft(
        candidate_id="G1M2U1L1",
        location="Work Time A (page 12)",
        standard_code="1.T.SS.1.a",
        clauses=[
            ClauseClientDraft(
                clause="identify text features",
                judgment="met",
                actor="student",
                student_quote=quote,
                teacher_quote="",
                why="directive elicitation",
            )
        ],
        alignment="full",
        needs_review=False,
        review_reason="",
        evidence="",
        anchor_note="",
    ).to_llm_draft()
    assert draft.matched_status == "full"
    assert draft.evidence == quote
    assert draft.evidence_candidates == [quote]
    assert draft.evidence_page == 12
    assert draft.confidence == "high"
    assert draft.clauses[0].met is True


def test_client_batch_draft_coerces_results_json_string():
    item = {
        "candidate_id": "G1M2U1L1",
        "location": "",
        "standard_code": "1.T.SS.1.a",
        "clauses": [
            {
                "clause": "identify text features",
                "judgment": "met",
                "actor": "student",
                "student_quote": "Have students point to the title page.",
                "teacher_quote": "",
                "why": "directive",
            }
        ],
        "alignment": "full",
        "needs_review": False,
        "review_reason": "",
        "evidence": "Students identify the title page.",
        "anchor_note": "",
    }
    draft = JudgeClientBatchDraft.model_validate({"results": json.dumps([item])})
    assert len(draft.results) == 1
    assert draft.results[0].standard_code == "1.T.SS.1.a"
    assert draft.results[0].alignment == "full"


def test_batch_default_max_tokens_starts_high_enough():
    assert DEFAULT_BATCH_MAX_TOKENS >= 16384


def test_client_draft_uses_student_quote_for_evidence_not_writeup():
    quote = "Have students point to the title page."
    writeup = (
        "Students identify the title page when directed. "
        "The lesson uses a structured read-aloud protocol."
    )
    draft = JudgeClientDraft(
        candidate_id="G1M2U1L1",
        location="Work Time A (page 12)",
        standard_code="1.T.SS.1.a",
        clauses=[
            ClauseClientDraft(
                clause="identify text features",
                judgment="met",
                actor="student",
                student_quote=quote,
                teacher_quote="",
                why="directive elicitation",
            )
        ],
        alignment="full",
        needs_review=False,
        review_reason="",
        evidence=writeup,
        anchor_note="",
    ).to_llm_draft()
    assert draft.evidence == quote
    assert draft.rationale == writeup


def test_client_needs_review_maps_to_low_confidence():
    draft = JudgeClientDraft(
        candidate_id="L",
        location="",
        standard_code="1.L.GC.1.16",
        clauses=[
            ClauseClientDraft(
                clause="use prepositions",
                judgment="met",
                actor="student",
                student_quote="Students complete the frame.",
                teacher_quote="",
                why="introduce tag",
            )
        ],
        alignment="full",
        needs_review=True,
        review_reason="partial-or-full — Introduce-tagged convention",
        evidence="Students complete the frame.",
        anchor_note="",
    ).to_llm_draft()
    assert draft.needs_review is True
    assert draft.confidence == "low"
    assert draft.evidence == "Students complete the frame."
    assert draft.rationale == "Students complete the frame."
    from veramynd_parser.judge.pipeline import _should_escalate

    assert _should_escalate(draft)


def test_cli_registers_judge_standards():
    parser = build_parser()
    args = parser.parse_args(
        [
            "judge-standards",
            "--retrieve-file",
            "output/retrieve/G1M2U1L3.json",
            "--lesson-file",
            "output/stage1/lessons/G1M2U1L3.json",
        ]
    )
    assert args.func.__name__ == "cmd_judge_standards"
    assert args.no_batch is False
    assert args.no_escalate is False


def test_cli_judge_no_escalate_opt_out():
    parser = build_parser()
    args = parser.parse_args(
        [
            "judge-standards",
            "--retrieve-file",
            "output/retrieve/G1M2U1L3.json",
            "--lesson-file",
            "output/stage1/lessons/G1M2U1L3.json",
            "--no-escalate",
        ]
    )
    assert args.no_escalate is True


def test_cli_judge_no_coverage_pass_opt_out():
    parser = build_parser()
    args = parser.parse_args(
        [
            "judge-standards",
            "--retrieve-file",
            "output/retrieve/G1M2U3L5.json",
            "--lesson-file",
            "output/stage1/lessons/G1M2U3L5.json",
            "--no-coverage-pass",
        ]
    )
    assert args.no_coverage_pass is True


def test_load_standard_raw_text_rejects_path_traversal(tmp_path: Path):
    standards = tmp_path / "standards"
    standards.mkdir()
    secret = tmp_path / "secret.json"
    secret.write_text(
        json.dumps({"raw_text": "leaked", "standard_code": "secret"}),
        encoding="utf-8",
    )
    with pytest.raises(JudgeIoError, match="unsafe"):
        load_standard_raw_text(standards, "../secret")
    with pytest.raises(JudgeIoError, match="unsafe"):
        load_standard_raw_text(standards, "..\\secret")
