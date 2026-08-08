"""Focused query builder prioritizes pedagogical signal over action floods."""

from __future__ import annotations

import json
from pathlib import Path

from veramynd_parser.retrieve.queries import (
    focused_queries_from_normalize,
    grade_from_normalize,
)


def _write_norm(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "resource_id": "G1M2U1L1",
                "provenance": {"grade": "1"},
                "level": "Grade 1",
                "learning_targets": [
                    {"text": "I can ask questions about observations."},
                    {"text": "I can ask questions about observations."},
                ],
                "objective": "Students observe and ask questions about the sun and moon.",
                "instructional_purpose": (
                    "Build observation, discussion, reading, and writing skills."
                ),
                "domain": {"primary": "Comprehension", "secondary": ["Vocabulary"]},
                "what_is_taught": [
                    {"skill": f"skill practice number {i} for students"}
                    for i in range(1, 8)
                ],
                "vocabulary": {"new": ["orbit", "shadow"], "review": ["sun"]},
                "evidence": [
                    {"quote": f"Evidence quote number {i} from the classroom lesson."}
                    for i in range(1, 5)
                ],
                "student_actions": {
                    f"action_{i}": f"Students do action number {i} carefully today."
                    for i in range(1, 10)
                },
                "teacher_actions": {
                    f"teach_{i}": f"Teacher models action number {i} for the class."
                    for i in range(1, 8)
                },
                "assessment": {"summary": "Exit ticket about observations and questions."},
                "discussion_prompts": [
                    {"prompt": "What do you notice and wonder about the sky?"}
                ],
                "writing_tasks": [
                    {"task": "Write and draw one observation about the moon."}
                ],
                "reading_tasks": [
                    {"task": "Read a short text and identify key details."}
                ],
            }
        ),
        encoding="utf-8",
    )


def test_focused_queries_prefer_vocab_evidence_over_action_flood(tmp_path: Path):
    norm = tmp_path / "G1M2U1L1.json"
    _write_norm(norm)
    qs = focused_queries_from_normalize(norm, max_queries=24)
    sources = [q["source"] for q in qs]
    assert any(s.startswith("learning_target_") for s in sources)
    assert "objective" in sources
    assert "instructional_purpose" in sources
    assert "vocabulary" in sources
    assert "domain_bridge" in sources
    assert any(s.startswith("discussion_prompt_") for s in sources)
    assert any(s.startswith("writing_task_") for s in sources)
    assert any(s.startswith("reading_task_") for s in sources)
    assert sources.count("student_action") <= 4
    assert sources.count("teacher_action") <= 0
    assert sum(1 for s in sources if s.startswith("evidence_")) <= 1
    assert len(qs) == len({q["text"].lower() for q in qs})
    assert all(len(q["text"]) <= 360 for q in qs)
    assert any(s.startswith("skill_") for s in sources)


def test_grade_from_normalize(tmp_path: Path):
    norm = tmp_path / "G1M2U1L1.json"
    _write_norm(norm)
    assert grade_from_normalize(norm) == 1


def test_domains_from_normalize(tmp_path: Path):
    from veramynd_parser.retrieve.queries import domains_from_normalize

    norm = tmp_path / "G1M2U1L1.json"
    _write_norm(norm)
    assert domains_from_normalize(norm) == ["Comprehension", "Vocabulary"]


def test_query_arm_weight_prefers_objective_and_vocab():
    from veramynd_parser.retrieve.queries import (
        query_arm_weight,
        query_counts_for_coverage,
    )

    assert query_arm_weight("objective") > query_arm_weight("evidence_1")
    assert query_arm_weight("vocabulary") > query_arm_weight("teacher_action")
    assert query_arm_weight("skill_1") > query_arm_weight("domain_bridge")
    assert query_counts_for_coverage("skill_1")
    assert query_counts_for_coverage("objective")
    assert not query_counts_for_coverage("domain_bridge")
    assert not query_counts_for_coverage("teacher_action")


def test_focused_queries_short_objective_fails_loud_not_empty(tmp_path: Path):
    """Regression: a record whose only field was a too-short title slipped past
    the fallback's elif chain (add() silently drops <12-char texts) and
    returned [] — surfacing far downstream as a misleading "no non-empty
    queries" error instead of this diagnostic."""
    import pytest

    path = tmp_path / "sparse.json"
    path.write_text(
        json.dumps({"resource_id": "G1M2U1L9", "title": "Cat"}),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="no usable fields"):
        focused_queries_from_normalize(path)


def test_writing_task_arm_found_beyond_first_evidence_item(tmp_path: Path):
    """Regression: evidence scanning broke at max_evidence (default 1), so a
    writing quote at evidence[1] never produced its writing_task arm."""
    path = tmp_path / "norm.json"
    path.write_text(
        json.dumps(
            {
                "resource_id": "G1M2U1L9",
                "objective": "Students write and draw one observation carefully.",
                "evidence": [
                    {
                        "quote": "Turn and tell your partner what you notice today.",
                        "evidence_role": "elicitation_check",
                        "supports_action": ["oral_production"],
                    },
                    {
                        "quote": "Students write one sentence about the moon phases.",
                        "supports_action": ["written_production"],
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    queries = focused_queries_from_normalize(path)
    sources = [q["source"] for q in queries]
    assert any(s.startswith("writing_task_evidence_") for s in sources)
