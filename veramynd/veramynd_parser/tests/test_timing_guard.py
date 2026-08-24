"""Tests for P5 invented while/after-reading timing guard."""

from __future__ import annotations

from veramynd_parser.judge.models import ClauseJudgment, JudgeLlmDraft
from veramynd_parser.judge.pipeline import judge_pair
from veramynd_parser.judge.timing_guard import (
    invents_reading_timing_requirement,
    scrub_invented_timing_rationale,
)


def test_detects_while_vs_after_timing_gate():
    bad = (
        "Students retell the story after reading, so this is only Partial "
        "because summarizing must occur while reading, not after."
    )
    assert invents_reading_timing_requirement(bad)
    good = (
        "Students summarize key points from the section and draw what they "
        "visualized; the summarize and visualize clauses are both met."
    )
    assert not invents_reading_timing_requirement(good)


def test_scrub_removes_timing_gate_sentence():
    raw = (
        "Students retell key events from the text. "
        "Because it happens only after reading rather than while reading, "
        "mark Partial. "
        "The visualize clause is also present in the response sheet."
    )
    cleaned, scrubbed = scrub_invented_timing_rationale(raw)
    assert scrubbed is True
    assert "after reading" not in cleaned.lower() or "P5:" in cleaned
    assert "P5:" in cleaned
    assert "retell key events" in cleaned.lower() or "visualize" in cleaned.lower()


def test_p5_judge_pair_scrubs_timing_and_flags_review():
    lesson = (
        "Students summarize what happened in the story and draw a picture "
        "of the main events on the response sheet."
    )

    def fake_complete(**kwargs):
        return JudgeLlmDraft(
            matched_status="partial",
            clauses=[
                ClauseJudgment(clause="summarize sections", met=True, note=""),
                ClauseJudgment(clause="visualize sections", met=True, note=""),
            ],
            evidence=lesson,
            evidence_page=1,
            confidence="high",
            rationale=(
                "Students summarize and visualize on the response sheet after "
                "reading. Mark Partial because the standard requires the skill "
                "while reading, not after reading."
            ),
            needs_review=False,
            review_reason="",
        )

    v = judge_pair(
        resource_id="G1M2U1L3",
        lesson_raw_text=lesson,
        standard={
            "standard_code": "1.P.EICC.3.d",
            "raw_text": "Summarize and visualize sections of the text to maintain understanding. (I)",
        },
        use_cache=False,
        escalate=False,
        complete_fn=fake_complete,
    )
    assert "P5:" in v.rationale
    assert v.needs_review is True
    assert "invented while/after-reading timing" in v.review_reason
    assert v.confidence == "low"
