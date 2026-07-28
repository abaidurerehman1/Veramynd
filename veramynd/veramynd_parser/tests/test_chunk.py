"""Production hierarchical chunker tests (lesson / instructional / evidence)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from veramynd_parser.chunk.builder import (
    KNOWN_EL_SECTIONS,
    block_chunk_id,
    build_block_text,
    build_lesson_bundle,
    build_lesson_text,
    chunk_lessons_dir,
    lesson_chunk_id,
)
from veramynd_parser.chunk.models import LessonChunkBundle
from veramynd_parser.cli import build_parser
from veramynd_parser.models import AgendaItem, InstructionalBlock, LearningTarget, Lesson
from veramynd_parser.normalize.models import (
    EvidenceItem,
    dump_ela_record_json,
    minimal_normalized_lesson,
)
from veramynd_parser.text_utils import parse_lesson_code


def _sample_lesson(code: str = "G1M2U1L1") -> Lesson:
    grade, module, unit, lesson_n = parse_lesson_code(code)
    return Lesson(
        code=code,
        grade=grade,
        module=module,
        unit=unit,
        lesson=lesson_n,
        title="Lesson 1: Observing",
        page_start=12,
        page_end=23,
        declared_standards=["SL.1.1"],
        learning_targets=[
            LearningTarget(text="I can describe what I observe.", codes=["SL.1.1"]),
        ],
        instructional_blocks=[
            InstructionalBlock(
                section="Opening",
                letter="A",
                title="Reading Aloud",
                page=16,
                minutes=15,
                steps=[
                    "Invite students to the rug.",
                    "Ask students what they notice in the pictures.",
                    "Turn and tell your partner what you notice.",
                    "Students turn and talk about their wonders.",
                ],
            ),
            InstructionalBlock(
                section="Work Time",
                letter="A",
                title="Noticing Chart",
                page=18,
                minutes=20,
                steps=[
                    "Record student observations on the chart.",
                    "Invite students to add one more wonder.",
                ],
            ),
            InstructionalBlock(
                section="Closing and Assessment",
                letter="A",
                title="Share",
                page=22,
                minutes=10,
                steps=[
                    "Invite students to share one observation with the class.",
                ],
            ),
        ],
        agenda=[
            AgendaItem(
                section="Opening", letter="A", title="Reading Aloud", minutes=15
            ),
            AgendaItem(
                section="Work Time", letter="A", title="Noticing Chart", minutes=20
            ),
            AgendaItem(
                section="Closing and Assessment", letter="A", title="Share", minutes=10
            ),
        ],
        materials=["Chart paper"],
        vocabulary=["observe (L)"],
    )


def test_lesson_text_skips_none_observed():
    norm = minimal_normalized_lesson()
    text = build_lesson_text(norm)
    assert "Domain primary: Speaking & Listening" in text
    assert "oral_production:" in text
    assert "NONE OBSERVED" not in text
    assert "Objective:" in text


def test_block_text_includes_steps():
    text = build_block_text(
        section="Work Time",
        letter="B",
        title="Close Read",
        steps=["Read aloud.", "Ask a question."],
    )
    assert text.startswith("[Work Time B] Close Read")
    assert "- Read aloud." in text


def test_build_bundle_joins_evidence_to_blocks():
    lesson = _sample_lesson()
    norm = minimal_normalized_lesson(resource_id=lesson.code)
    norm = norm.model_copy(
        update={
            "evidence": list(norm.evidence)
            + [
                EvidenceItem(
                    quote="Invite students to share one observation with the class.",
                    location="Closing and Assessment A",
                    actor="student",
                    evidence_role="directive_prompt",
                    support="independent",
                    supports_action=["oral_production"],
                )
            ]
        }
    )
    bundle = build_lesson_bundle(lesson, norm)
    assert bundle.lesson_chunk.chunk_id == lesson_chunk_id(lesson.code)
    assert bundle.lesson_chunk.family == "lesson"
    assert len(bundle.instructional_chunks) == 3
    assert {c.section for c in bundle.instructional_chunks} == set(KNOWN_EL_SECTIONS)
    closing_id = block_chunk_id(lesson.code, "Closing and Assessment", "A")
    assert any(c.chunk_id == closing_id for c in bundle.instructional_chunks)
    assert len(bundle.evidence_pointers) == 2
    assert all(p.family == "evidence_pointer" for p in bundle.evidence_pointers)
    assert bundle.evidence_pointers[0].block_chunk_id == block_chunk_id(
        lesson.code, "Opening", "A"
    )
    assert bundle.evidence_pointers[1].block_chunk_id == closing_id


def test_build_bundle_rejects_unjoined_location():
    lesson = _sample_lesson()
    norm = minimal_normalized_lesson(resource_id=lesson.code)
    norm = norm.model_copy(
        update={
            "evidence": [
                EvidenceItem(
                    quote="Turn and tell your partner what you notice.",
                    location="Work Time Z",
                    actor="student",
                    evidence_role="directive_prompt",
                    support="with_prompting",
                    supports_action=["oral_production"],
                )
            ]
        }
    )
    with pytest.raises(ValueError, match="does not join"):
        build_lesson_bundle(lesson, norm)


def test_build_bundle_accepts_publisher_section_labels():
    """K–12 / multi-publisher: Stage-1 section strings are not EL-only."""
    lesson = _sample_lesson()
    other = lesson.model_copy(
        update={
            "instructional_blocks": [
                InstructionalBlock(
                    section="Warm-Up",
                    letter="A",
                    title="Do Now",
                    page=1,
                    steps=["Students complete the do-now on the board."],
                ),
                InstructionalBlock(
                    section="Guided Practice",
                    letter="B",
                    title="Model",
                    page=2,
                    steps=["Teacher models the strategy aloud."],
                ),
            ]
        }
    )
    norm = minimal_normalized_lesson(resource_id=lesson.code)
    norm = norm.model_copy(
        update={
            "evidence": [
                EvidenceItem(
                    quote="Students complete the do-now on the board.",
                    location="Warm-Up A",
                    actor="student",
                    evidence_role="directive_prompt",
                    support="independent",
                    supports_action=["written_production"],
                )
            ]
        }
    )
    bundle = build_lesson_bundle(other, norm)
    assert {c.section for c in bundle.instructional_chunks} == {
        "Warm-Up",
        "Guided Practice",
    }
    assert bundle.evidence_pointers[0].block_chunk_id == block_chunk_id(
        lesson.code, "Warm-Up", "A"
    )


def test_build_bundle_rejects_empty_section():
    lesson = _sample_lesson()
    bad = lesson.model_copy(
        update={
            "instructional_blocks": [
                InstructionalBlock(
                    section="   ",
                    letter="A",
                    title="x",
                    page=1,
                    steps=["Do a thing."],
                )
            ]
        }
    )
    with pytest.raises(ValueError, match="missing section"):
        build_lesson_bundle(bad, minimal_normalized_lesson(resource_id=lesson.code))


def test_chunk_lessons_dir_writes_bundles(tmp_path: Path):
    lessons_dir = tmp_path / "lessons"
    normalize_dir = tmp_path / "normalize"
    out_dir = tmp_path / "chunks"
    lessons_dir.mkdir()
    normalize_dir.mkdir()

    lesson = _sample_lesson("G1M2U1L1")
    (lessons_dir / "G1M2U1L1.json").write_text(
        lesson.model_dump_json(indent=2) + "\n", encoding="utf-8"
    )
    norm = minimal_normalized_lesson(resource_id="G1M2U1L1")
    (normalize_dir / "G1M2U1L1.json").write_text(
        dump_ela_record_json(norm), encoding="utf-8"
    )

    manifest = chunk_lessons_dir(lessons_dir, normalize_dir, out_dir)
    assert manifest["lessons"] == 1
    assert manifest["lesson_chunks"] == 1
    assert manifest["instructional_chunks"] == 3
    assert manifest["evidence_pointers"] == 1
    assert manifest["sections_policy"] == "stage1_labels"
    assert not manifest["failed"]
    assert "embed_lesson_jsonl" not in manifest["outputs"]

    bundle_path = out_dir / "by_lesson" / "G1M2U1L1.json"
    assert bundle_path.is_file()
    bundle = LessonChunkBundle.model_validate_json(
        bundle_path.read_text(encoding="utf-8")
    )
    assert bundle.resource_id == "G1M2U1L1"
    assert "oral_production" in bundle.lesson_chunk.text
    assert not hasattr(bundle.lesson_chunk, "embed") or "embed" not in bundle.lesson_chunk.model_dump()

    assert not (out_dir / "embed_lesson.jsonl").exists()
    assert not (out_dir / "embed_block.jsonl").exists()

    progress = json.loads((out_dir / "chunk_progress.json").read_text(encoding="utf-8"))
    assert progress["status"] == "complete"


def test_cli_chunk_lessons_wires():
    args = build_parser().parse_args(
        [
            "chunk-lessons",
            "output/stage1/lessons",
            "--normalize-dir",
            "output/normalize",
            "--out",
            "output/chunks",
        ]
    )
    assert args.func.__name__ == "cmd_chunk_lessons"
    assert args.lessons_dir == "output/stage1/lessons"
    assert args.normalize_dir == "output/normalize"
    assert args.out == "output/chunks"
