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
from veramynd_parser.judge.models import ClauseJudgment, JudgeLlmDraft
from veramynd_parser.judge.pipeline import judge_pair, judge_retrieve_file


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
            clauses=[clause],
            evidence="",
            evidence_page=1,
            confidence="high",
            rationale="r",
        )
    )


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
