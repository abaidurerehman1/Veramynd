"""Conformance: dumped ELA records must match ela_normalization_template.blank.json."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from veramynd_parser.normalize.models import (
    DomainBlock,
    EvidenceItem,
    NormalizedLesson,
    StudentActions,
    SubjectProfile,
    TaughtSkill,
    TeacherActions,
    TextComplexity,
    dump_ela_record,
    minimal_normalized_lesson,
)

_SCHEMA_DIR = Path(__file__).resolve().parents[1] / "veramynd_parser" / "schemas"
_BLANK = _SCHEMA_DIR / "ela_normalization_template.blank.json"


def test_blank_template_file_present():
    assert _BLANK.is_file(), f"missing blank template at {_BLANK}"


def test_dumped_keys_match_blank_template_exactly():
    blank = json.loads(_BLANK.read_text(encoding="utf-8"))
    template_keys = {k for k in blank.keys() if k != "_comment"}
    dumped = dump_ela_record(minimal_normalized_lesson())
    body_keys = {k for k in dumped.keys() if k != "_pipeline"}
    assert body_keys == template_keys, (
        f"extra={body_keys - template_keys} missing={template_keys - body_keys}"
    )


def test_nested_required_blocks_match_blank():
    blank = json.loads(_BLANK.read_text(encoding="utf-8"))
    dumped = dump_ela_record(minimal_normalized_lesson())

    assert set(dumped["provenance"].keys()) == set(blank["provenance"].keys())
    assert set(dumped["placement"].keys()) == set(blank["placement"].keys())
    assert set(dumped["placement"]["hierarchy"].keys()) == set(
        blank["placement"]["hierarchy"].keys()
    )
    assert set(dumped["student_actions"].keys()) == set(blank["student_actions"].keys())
    assert set(dumped["evidence"][0].keys()) == set(blank["evidence"][0].keys())
    assert set(dumped["teacher_actions"].keys()) == set(blank["teacher_actions"].keys())
    assert set(dumped["context"].keys()) == set(blank["context"].keys())
    assert set(dumped["sections_covered"].keys()) == set(blank["sections_covered"].keys())
    assert set(dumped["supports"].keys()) == set(blank["supports"].keys())
    assert set(dumped["assessment"].keys()) == set(blank["assessment"].keys())
    assert set(dumped["vocabulary"].keys()) == set(blank["vocabulary"].keys())


def test_non_comprehension_omits_text_complexity():
    dumped = dump_ela_record(minimal_normalized_lesson())
    assert "text_complexity" not in dumped["subject_profile"]
    assert dumped["subject_profile"]["mode"] in ("interpretation", "construction", "both")
    assert dumped["assessment"]["recognition_vs_production"] is None


def test_comprehension_requires_real_text_complexity_not_na():
    with pytest.raises(ValidationError, match="text_complexity"):
        NormalizedLesson(
            resource_id="G1M2U1L1",
            title="t",
            domain=DomainBlock(primary="Comprehension"),
            objective="o",
            what_is_taught=[
                TaughtSkill(skill="retell", cognitive_demand="DOK2_skills_concepts")
            ],
            student_actions=StudentActions(
                comprehension_response="Answer questions about the text.",
            ),
            evidence=[
                EvidenceItem(
                    quote="Ask and answer questions about key details.",
                    location="Work Time A",
                    actor="student",
                    evidence_role="elicitation_check",
                    support="with_prompting",
                    supports_action=["comprehension_response"],
                )
            ],
            teacher_actions=TeacherActions(with_prompting_and_support="yes"),
            subject_profile=SubjectProfile(
                mode="interpretation",
                genre="narrative",
                text_complexity=TextComplexity(
                    quantitative="n/a",
                    qualitative="n/a",
                ),
            ),
        )


def test_comprehension_dump_includes_text_complexity():
    norm = NormalizedLesson(
        resource_id="G1M2U1L1",
        title="t",
        domain=DomainBlock(primary="Comprehension"),
        objective="Students answer questions about a read-aloud.",
        what_is_taught=[
            TaughtSkill(skill="answer key-detail questions", cognitive_demand="DOK2_skills_concepts")
        ],
        student_actions=StudentActions(
            comprehension_response="Answer questions about key details.",
        ),
        evidence=[
            EvidenceItem(
                quote="Ask and answer questions about key details.",
                location="Work Time A",
                actor="student",
                evidence_role="elicitation_check",
                support="with_prompting",
                supports_action=["comprehension_response"],
            )
        ],
        teacher_actions=TeacherActions(with_prompting_and_support="yes"),
        subject_profile=SubjectProfile(
            mode="interpretation",
            genre="narrative",
            text_complexity=TextComplexity(
                quantitative="read-aloud; above band, teacher-mediated",
                qualitative="simple narrative structure; concrete language",
            ),
        ),
    )
    dumped = dump_ela_record(norm)
    assert "text_complexity" in dumped["subject_profile"]
    assert dumped["subject_profile"]["text_complexity"]["quantitative"]
    assert "reader_and_task" not in dumped["subject_profile"]["text_complexity"]


def test_rejects_unknown_supports_action_key():
    with pytest.raises(ValidationError, match="unknown key"):
        NormalizedLesson(
            resource_id="G1M2U1L1",
            title="t",
            domain=DomainBlock(primary="Speaking & Listening"),
            objective="o",
            what_is_taught=[
                TaughtSkill(skill="talk", cognitive_demand="DOK1_recall_reproduction")
            ],
            student_actions=StudentActions(oral_production="Talk."),
            evidence=[
                EvidenceItem(
                    quote="Turn and talk.",
                    location="Opening",
                    actor="student",
                    evidence_role="directive_prompt",
                    support="with_prompting",
                    supports_action=["not_a_real_action"],
                )
            ],
            teacher_actions=TeacherActions(with_prompting_and_support="yes"),
            subject_profile=SubjectProfile(mode="interpretation", genre="n/a"),
        )


def test_secondary_comprehension_requires_genre_and_text_complexity():
    with pytest.raises(ValidationError, match="genre"):
        NormalizedLesson(
            resource_id="G1M2U1L1",
            title="t",
            domain=DomainBlock(
                primary="Speaking & Listening",
                secondary=["Comprehension"],
            ),
            objective="o",
            what_is_taught=[
                TaughtSkill(skill="discuss a story", cognitive_demand="DOK2_skills_concepts")
            ],
            student_actions=StudentActions(
                oral_production="Turn and talk about the story.",
            ),
            evidence=[
                EvidenceItem(
                    quote="Turn and tell your partner what you notice.",
                    location="Opening A",
                    actor="student",
                    evidence_role="directive_prompt",
                    support="with_prompting",
                    supports_action=["oral_production"],
                )
            ],
            teacher_actions=TeacherActions(with_prompting_and_support="yes"),
            subject_profile=SubjectProfile(mode="interpretation", genre="n/a"),
        )


def test_writing_requires_genre():
    with pytest.raises(ValidationError, match="genre"):
        NormalizedLesson(
            resource_id="G1M2U1L1",
            title="t",
            domain=DomainBlock(primary="Writing"),
            objective="o",
            what_is_taught=[
                TaughtSkill(skill="write", cognitive_demand="DOK2_skills_concepts")
            ],
            student_actions=StudentActions(written_production="Write a sentence."),
            evidence=[
                EvidenceItem(
                    quote="Write a sentence about the sky.",
                    location="Work Time",
                    actor="student",
                    evidence_role="directive_prompt",
                    support="with_prompting",
                    supports_action=["written_production"],
                )
            ],
            teacher_actions=TeacherActions(with_prompting_and_support="yes"),
            subject_profile=SubjectProfile(mode="construction", genre="n/a"),
        )
