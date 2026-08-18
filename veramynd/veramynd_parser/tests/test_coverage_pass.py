"""P6 activity coverage pass (judge-time inject, retrieve ranking unchanged)."""

from __future__ import annotations

import json
from pathlib import Path

from veramynd_parser.judge.coverage import (
    apply_activity_coverage_pass,
    detect_activity_families,
    load_retrieve_pool,
)
from veramynd_parser.judge.io import lesson_raw_text_from_stage1
from veramynd_parser.judge.models import (
    ClauseJudgment,
    JudgeLlmDraft,
)
from veramynd_parser.judge.pipeline import judge_retrieve_file


def test_detects_student_feedback_not_title_only():
    families = detect_activity_families(
        "Tell students they are going to provide feedback on a classmate's writing."
    )
    assert {f.name for f in families} == {"feedback"}


def test_teacher_praise_alone_does_not_fire_feedback():
    families = detect_activity_families(
        "Give students specific, positive feedback on their ability to plan."
    )
    assert families == []


def test_coverage_pass_appends_after_top_n_and_keeps_order():
    selected = [{"standard_code": f"S{i}"} for i in range(25)]
    pool = {
        "1.P.CP.1.c": {"standard_code": "1.P.CP.1.c", "rrf_rank": 47},
        "1.P.EICC.4.f": {"standard_code": "1.P.EICC.4.f", "rerank_rank": 79},
        "1.P.CP.2.a": {"standard_code": "1.P.CP.2.a", "rerank_rank": 38},
    }
    lesson = (
        "I can provide kind, helpful, and specific feedback to my classmates. "
        "Students use the partners protocol to share their writing."
    )
    out, injected = apply_activity_coverage_pass(
        selected,
        lesson_text=lesson,
        pool=pool,
        available_codes=set(pool),
    )
    assert [c["standard_code"] for c in out[:25]] == [f"S{i}" for i in range(25)]
    assert set(injected) >= {"1.P.EICC.4.f", "1.P.CP.1.c", "1.P.CP.2.a"}
    assert all(c.get("coverage_pass") for c in out[25:])


def test_coverage_pass_noop_when_already_in_shortlist():
    selected = [{"standard_code": "1.P.CP.1.c"}]
    out, injected = apply_activity_coverage_pass(
        selected,
        lesson_text="Students provide feedback to partners.",
        pool={"1.P.CP.1.c": {"standard_code": "1.P.CP.1.c"}},
        available_codes={"1.P.CP.1.c"},
    )
    assert injected == [] or "1.P.CP.1.c" not in injected
    assert [c["standard_code"] for c in out][0] == "1.P.CP.1.c"


def test_coverage_pass_skips_codes_not_in_pool_or_standards_dir():
    out, injected = apply_activity_coverage_pass(
        [{"standard_code": "1.T.T.1.a"}],
        lesson_text="Students provide feedback to classmates.",
        pool={},
        available_codes={"1.T.T.1.a"},
    )
    assert injected == []
    assert [c["standard_code"] for c in out] == ["1.T.T.1.a"]


def test_judge_retrieve_limit_then_coverage_inject(tmp_path: Path):
    lesson_path = tmp_path / "L.json"
    lesson_path.write_text(
        json.dumps(
            {
                "code": "G1M2U3L5",
                "title": "Lesson 5",
                "instructional_blocks": [
                    {
                        "section": "Work Time",
                        "letter": "C",
                        "title": "Peer Feedback",
                        "page": 10,
                        "steps": [
                            "Tell students they are going to provide feedback "
                            "on a classmate's writing."
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
                    {"standard_code": "1.T.T.1.a", "rrf_score": 0.9},
                    {"standard_code": "1.T.T.1.b", "rrf_score": 0.8},
                    {"standard_code": "1.T.T.1.c", "rrf_score": 0.7},
                ],
                "reranked_candidates": [
                    {
                        "standard_code": "1.P.CP.1.c",
                        "rerank_score": 0.1,
                        "rerank_rank": 47,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    std_dir = tmp_path / "stds"
    std_dir.mkdir()
    for code, raw in (
        ("1.T.T.1.a", "Identify characters."),
        ("1.T.T.1.b", "Compare characters."),
        ("1.P.CP.1.c", "Contribute to discussions by providing feedback."),
    ):
        (std_dir / f"{code}.json").write_text(
            json.dumps(
                {
                    "standard_code": code,
                    "raw_text": raw,
                    "competency_statement": raw,
                    "domain": {"primary": "Practices"},
                }
            ),
            encoding="utf-8",
        )

    def fake_complete(**kwargs):
        return JudgeLlmDraft(
            matched_status="none",
            clauses=[ClauseJudgment(clause="x", met=False, note="not met")],
            evidence="",
            evidence_page=None,
            confidence="high",
            rationale="",
        )

    report = judge_retrieve_file(
        retrieve_file=retrieve_path,
        standards_dir=std_dir,
        lesson_file=lesson_path,
        use_cache=False,
        escalate=False,
        limit=1,
        complete_fn=fake_complete,
    )
    codes = [v["standard_code"] for v in report["verdicts"]]
    assert codes[0] == "1.T.T.1.a"
    assert "1.P.CP.1.c" in codes
    assert "1.P.CP.1.c" in report["coverage_pass_injected"]
    meta = report["verdicts"][-1]["retrieval"]
    assert meta.get("coverage_pass") is True


def test_u3l5_stage1_triggers_feedback_and_present():
    path = Path("output/stage1/lessons/G1M2U3L5.json")
    if not path.is_file():
        return
    lesson = json.loads(path.read_text(encoding="utf-8"))
    text = lesson_raw_text_from_stage1(lesson)
    names = {f.name for f in detect_activity_families(text)}
    assert "feedback" in names
    assert "present" in names
