"""P4 input-scope caveat: missing supporting read-aloud guides."""

from __future__ import annotations

from veramynd_parser.judge.input_scope import (
    INPUT_SCOPE_CAVEAT,
    input_scope_caveat,
    missing_readaloud_guide,
    readaloud_guide_body_present,
)
from veramynd_parser.judge.models import ClauseJudgment, JudgeLlmDraft
from veramynd_parser.judge.pipeline import judge_pair

_POINTER = (
    "Guide students through the close read-aloud for Summer Sun Risin' using "
    "the Close Readaloud Guide: Summer Sun Risin' (Session 1; for teacher "
    "reference). Consider using the Reading Literature Checklist."
)

_GUIDE_BODY = """
[Work Time A] Close Read-aloud Guide: Summer Sun Risin' Session 1 (page 12)
- Ask: Who is the boy in this story?
- Ask: What does the sun do at the beginning?
- What is the setting of this page?
- Why does the boy look at the sky?
"""


def test_pointer_only_is_missing_guide():
    assert missing_readaloud_guide(_POINTER)
    assert not readaloud_guide_body_present(_POINTER)


def test_ingested_guide_body_clears_missing_flag():
    assert readaloud_guide_body_present(_GUIDE_BODY)
    assert not missing_readaloud_guide(_GUIDE_BODY)


def test_no_guide_cite_is_not_missing():
    assert not missing_readaloud_guide(
        "Students identify the setting of the story."
    )


def test_caveat_only_on_named_comprehension_codes():
    assert input_scope_caveat("1.T.T.1.a", _POINTER) == INPUT_SCOPE_CAVEAT
    assert input_scope_caveat("1.P.EICC.3.f", _POINTER) == INPUT_SCOPE_CAVEAT
    assert input_scope_caveat("1.L.V.1.a", _POINTER) == ""
    assert input_scope_caveat("1.T.T.1.a", "Students identify the setting.") == ""


def test_judge_pair_discloses_missing_guide_without_changing_label():
    def fake_complete(**kwargs):
        return JudgeLlmDraft(
            matched_status="partial",
            clauses=[
                ClauseJudgment(clause="identify setting", met=True, note=""),
                ClauseJudgment(clause="identify dialogue", met=False, note=""),
            ],
            evidence=_POINTER,
            evidence_page=70,
            confidence="high",
            rationale="Setting is practiced; dialogue is not.",
        )

    v = judge_pair(
        resource_id="G1M2U1L3",
        lesson_raw_text=_POINTER,
        standard={
            "standard_code": "1.T.T.1.a",
            "raw_text": "Identify characters, setting, major events, and dialogue.",
        },
        use_cache=False,
        escalate=False,
        complete_fn=fake_complete,
    )
    assert v.matched_status == "partial"
    assert v.input_scope_caveat == INPUT_SCOPE_CAVEAT
    assert v.needs_review is False


def test_judge_pair_no_caveat_when_guide_is_in_the_lesson():
    def fake_complete(**kwargs):
        quote = "Ask: Who is the boy in this story?"
        return JudgeLlmDraft(
            matched_status="partial",
            clauses=[
                ClauseJudgment(clause="identify characters", met=True, note=""),
                ClauseJudgment(clause="identify dialogue", met=False, note=""),
            ],
            evidence=quote,
            evidence_page=12,
            confidence="high",
            rationale="Characters identified; dialogue is not.",
        )

    v = judge_pair(
        resource_id="G1M2U1L3",
        lesson_raw_text=_GUIDE_BODY,
        standard={
            "standard_code": "1.T.T.1.a",
            "raw_text": "Identify characters, setting, major events, and dialogue.",
        },
        use_cache=False,
        escalate=False,
        complete_fn=fake_complete,
    )
    assert v.matched_status == "partial"
    assert v.input_scope_caveat == ""
