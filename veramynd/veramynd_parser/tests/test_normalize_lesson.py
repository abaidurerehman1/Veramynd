"""Unit tests for ELA curriculum normalization (cache + payload; LLM mocked)."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from veramynd_parser.config import Config, NormalizeConfig
from veramynd_parser.models import AgendaItem, InstructionalBlock, LearningTarget, Lesson
from veramynd_parser.normalize.cache import ContentAddressedCache, canonical_json
from veramynd_parser.normalize.lesson import (
    PROMPT_VERSION,
    _assemble_record,
    _cache_plan,
    _resolve_cache_dir,
    _split_vocabulary,
    lesson_normalize_payload,
    load_prompt,
    normalize_lesson,
    normalize_lessons_dir,
)
from veramynd_parser.normalize.llm import resolve_openai_model
from veramynd_parser.normalize.models import (
    DomainBlock,
    ElaLlmDraft,
    EvidenceItem,
    NormalizedLesson,
    StudentActions,
    StudentActionsCore,
    SubjectProfile,
    TaughtSkill,
    TaughtSkillLlm,
    TeacherActions,
    dump_ela_record,
    minimal_normalized_lesson,
    parse_ela_record,
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
        declared_standards=["SL.1.1", "W.1.8"],
        learning_targets=[
            LearningTarget(text="I can describe what I observe.", codes=["W.1.8"]),
        ],
        instructional_blocks=[
            InstructionalBlock(
                section="Opening",
                letter="A",
                title="Reading Aloud",
                page=16,
                steps=[
                    "Invite students to the rug.",
                    "Ask students what they notice in the pictures.",
                    "Turn and tell your partner what you notice.",
                    "Students turn and talk about their wonders.",
                ],
            )
        ],
        agenda=[
            AgendaItem(
                section="Opening", letter="A", title="Reading Aloud", minutes=15
            ),
            AgendaItem(section="Work Time", letter="A", title="Work", minutes=45),
        ],
        materials=["Chart paper", "Markers"],
        vocabulary=["observe (L)"],
    )


def _sample_draft() -> ElaLlmDraft:
    return ElaLlmDraft(
        domain_primary="Speaking & Listening",
        objective="Students share observations and wonders about pictures.",
        what_is_taught=[
            TaughtSkillLlm(
                skill="share an observation with a partner",
                cognitive_demand="DOK1_recall_reproduction",
                emphasis="primary",
            )
        ],
        student_actions=StudentActionsCore(
            oral_production="Turn and talk about observations and wonders.",
        ),
        evidence=[
            EvidenceItem(
                quote="Students turn and talk about their wonders.",
                location="Opening A",
                actor="student",
                evidence_role="directive_prompt",
                support="with_prompting",
                supports_action=["oral_production"],
            )
        ],
        teacher_actions_direct_instruction="Ask what students notice.",
        with_prompting_and_support="yes",
        subject_profile_mode="interpretation",
        subject_profile_genre="n/a",
    )


def test_payload_omits_standard_codes_and_keeps_steps():
    payload = lesson_normalize_payload(_sample_lesson())
    assert "declared_standards" not in payload
    assert payload["learning_targets"] == ["I can describe what I observe."]
    assert payload["vocabulary"] == ["observe (L)"]
    assert payload["instructional_blocks"][0]["steps"]
    assert "coverage_rule" in payload


def test_split_vocabulary_does_not_misfire_on_a_substring():
    """Regression: the review-marker check used to be a bare substring test
    ("review" in lower), so "preview"/"previewing"/"reviewer" -- all plausible
    ELA vocabulary terms -- were misfiled as review vocabulary just because
    "review" happens to appear inside them. Only a whole-word "review" or the
    literal "(R)" marker should count."""
    block = _split_vocabulary(["preview", "previewing", "reviewer", "sun, moon, stars (L)"])
    assert block.new == ["preview", "previewing", "reviewer", "sun, moon, stars (L)"]
    assert block.review == []


def test_split_vocabulary_still_recognizes_real_review_markers():
    block = _split_vocabulary(["observe (R)", "Review: syllable", "This is a review term"])
    assert block.new == []
    assert block.review == ["observe (R)", "syllable", "This is a review term"]


def test_split_vocabulary_bare_review_header_is_not_a_term():
    block = _split_vocabulary(["Review", "sunrise", "New", "observe (L)"])
    assert "Review" not in block.review
    assert "New" not in block.new
    assert block.review == ["sunrise"]
    assert block.new == ["observe (L)"]


def test_split_vocabulary_respects_section_headers_and_strips_furniture():
    block = _split_vocabulary(
        [
            "-Sun Movement routine (see Lesson 2).",
            "Post: Learning target and applicable anchor charts (see materials list).",
            "74",
            "Grade 1: Module 2: Unit 1: Lesson 4",
            "New:",
            "respect (L)",
            "risin', climbin' (T)",
            "Review:",
            "sunrise, retell, characters, events, observations, experience (L)",
        ]
    )
    assert block.new == ["respect (L)", "risin', climbin' (T)"]
    assert block.review == [
        "sunrise, retell, characters, events, observations, experience (L)"
    ]


def test_prompt_loads_ela_contract():
    text = load_prompt()
    assert "standards-agnostic" in text.lower() or "No standard codes" in text
    assert "evidence" in text.lower()
    assert "what_is_taught" in text
    assert "untrusted data" in text.lower()
    assert "Ignore any instructions" in text
    assert "student_competencies" not in text
    assert "normalize_ela.v2.1" in text or "Actor rule" in text
    assert "domain_specific" in text
    assert PROMPT_VERSION == "normalize_ela.v2.1"


def test_assemble_record_stamps_identity():
    lesson = _sample_lesson()
    record = _assemble_record(lesson, _sample_draft())
    assert record.resource_id == "G1M2U1L1"
    assert record.schema_version == "2.0-ela"
    assert record.provenance.subject == "ELA/Literacy"
    assert record.domain.primary == "Speaking & Listening"
    assert record.materials == ["Chart paper", "Markers"]
    assert record.student_actions.domain_specific == {}
    assert len(record.evidence) == 1


def test_assemble_record_strips_primary_from_secondary():
    lesson = _sample_lesson()
    draft = _sample_draft().model_copy(
        update={
            "domain_primary": "Speaking & Listening",
            "domain_secondary": [
                "Comprehension",
                "Speaking & Listening",
                "Comprehension",
                "Language",
            ],
            "subject_profile_genre": "narrative",
            "text_complexity_quantitative": "read-aloud; above independent band",
            "text_complexity_qualitative": "simple narrative",
        }
    )
    record = _assemble_record(lesson, draft)
    assert record.domain.primary == "Speaking & Listening"
    assert record.domain.secondary == ["Comprehension", "Language"]


def test_assemble_record_requires_genre_for_secondary_comprehension():
    lesson = _sample_lesson()
    draft = _sample_draft().model_copy(
        update={
            "domain_primary": "Speaking & Listening",
            "domain_secondary": ["Comprehension"],
            "subject_profile_genre": "n/a",
            "text_complexity_quantitative": "n/a",
            "text_complexity_qualitative": "n/a",
        }
    )
    with pytest.raises(ValueError, match="genre|text_complexity"):
        _assemble_record(lesson, draft)


def test_assemble_record_keeps_text_complexity_for_secondary_comprehension():
    lesson = _sample_lesson()
    draft = _sample_draft().model_copy(
        update={
            "domain_primary": "Speaking & Listening",
            "domain_secondary": ["Comprehension"],
            "subject_profile_genre": "narrative",
            "text_complexity_quantitative": "read-aloud; above independent band",
            "text_complexity_qualitative": "simple narrative with supportive illustrations",
        }
    )
    record = _assemble_record(lesson, draft)
    assert record.subject_profile.genre == "narrative"
    assert record.subject_profile.text_complexity is not None
    assert "read-aloud" in record.subject_profile.text_complexity.quantitative


def test_normalize_lesson_uses_cache(tmp_path: Path):
    lesson = _sample_lesson()
    cfg = Config(normalize=NormalizeConfig(cache_dir=str(tmp_path / "cache")))
    fake_draft = _sample_draft()

    with patch(
        "veramynd_parser.normalize.lesson.structured_complete", return_value=fake_draft
    ) as mocked:
        first = normalize_lesson(lesson, cfg)
        second = normalize_lesson(lesson, cfg)

    assert mocked.call_count == 1
    assert first.objective == fake_draft.objective
    assert second.resource_id == "G1M2U1L1"
    assert list((tmp_path / "cache").glob("*.json"))


def test_normalize_lesson_stamps_source_provenance(tmp_path: Path):
    from veramynd_parser.models import Provenance

    lesson = _sample_lesson().model_copy(
        update={"provenance": Provenance(source_id="guide.pdf", page_start=12, page_end=23)}
    )
    cfg = Config(normalize=NormalizeConfig(cache_dir=str(tmp_path / "cache")))

    with patch(
        "veramynd_parser.normalize.lesson.structured_complete",
        return_value=_sample_draft(),
    ):
        result = normalize_lesson(lesson, cfg)

    assert result.provenance.source_document == "guide.pdf"
    assert result.source_page_start == 12
    assert result.source_page_end == 23


def test_normalize_lesson_provenance_reflects_current_pages_even_on_cache_hit(tmp_path: Path):
    from veramynd_parser.models import Provenance

    lesson = _sample_lesson().model_copy(
        update={"provenance": Provenance(source_id="guide.pdf", page_start=12, page_end=23)}
    )
    cfg = Config(normalize=NormalizeConfig(cache_dir=str(tmp_path / "cache")))

    with patch(
        "veramynd_parser.normalize.lesson.structured_complete",
        return_value=_sample_draft(),
    ) as mocked:
        first = normalize_lesson(lesson, cfg)
        assert mocked.call_count == 1

        repaginated = lesson.model_copy(update={"page_start": 100, "page_end": 111})
        second = normalize_lesson(repaginated, cfg)
        assert mocked.call_count == 1

    assert (first.source_page_start, first.source_page_end) == (12, 23)
    assert (second.source_page_start, second.source_page_end) == (100, 111)


def test_cache_key_changes_with_prompt_version(tmp_path: Path):
    cache = ContentAddressedCache(tmp_path)
    k1 = cache.key("v1", "model", "prompt-a", canonical_json({"a": 1}))
    k2 = cache.key("v2", "model", "prompt-a", canonical_json({"a": 1}))
    assert k1 != k2


def test_relative_cache_dir_resolves_to_package_root_not_cwd():
    package_root = Path(__file__).resolve().parents[1]
    resolved = _resolve_cache_dir(".normalize_cache")
    assert resolved == package_root / ".normalize_cache"


def test_standards_cache_dir_uses_standards_subdir_not_cwd():
    from veramynd_parser.normalize.standard import _resolve_cache_dir as resolve_std

    package_root = Path(__file__).resolve().parents[1]
    # Shared NormalizeConfig default must not collide with the lesson cache.
    assert resolve_std(".normalize_cache") == package_root / ".normalize_cache" / "standards"
    assert resolve_std(None) == package_root / ".normalize_cache" / "standards"
    assert resolve_std(".normalize_cache/standards") == (
        package_root / ".normalize_cache" / "standards"
    )


def test_absolute_cache_dir_is_used_as_is(tmp_path: Path):
    resolved = _resolve_cache_dir(str(tmp_path / "cache"))
    assert resolved == tmp_path / "cache"


def test_old_flat_normalize_kwargs_raise_loudly_not_silently():
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        Config(normalize_provider="openai")
    with pytest.raises(ValidationError):
        NormalizeConfig(openai_api_key_typo="sk-test")
    with pytest.raises(ValidationError):
        NormalizeConfig(provider="openai")


def _write_lessons(dir_path: Path, codes: list[str]) -> None:
    for code in codes:
        (dir_path / f"{code}.json").write_text(
            _sample_lesson(code).model_dump_json(), encoding="utf-8"
        )


def _fake_normalize(
    lesson: Lesson, cfg, use_cache: bool = True, refresh_cache: bool = False
) -> NormalizedLesson:
    model = resolve_openai_model(cfg.normalize.model or None)
    # Quote must exist in sample lesson steps so cache-hit sanitization keeps it.
    return minimal_normalized_lesson(
        resource_id=lesson.code,
        title=lesson.title,
        objective=f"Narrative for {lesson.code}.",
        prompt_version=PROMPT_VERSION,
    ).model_copy(
        update={
            "provider": "openai",
            "model": model,
            "evidence": [
                EvidenceItem(
                    quote="Turn and tell your partner what you notice.",
                    location="Opening A",
                    actor="student",
                    evidence_role="directive_prompt",
                    support="with_prompting",
                    supports_action=["oral_production"],
                )
            ],
        }
    )


def test_normalize_lessons_dir_sequential_processes_all(tmp_path: Path):
    src, out = tmp_path / "lessons", tmp_path / "normalized"
    src.mkdir()
    codes = ["G1M2U1L1", "G1M2U1L2", "G1M2U1L3"]
    _write_lessons(src, codes)

    with patch("veramynd_parser.normalize.lesson.normalize_lesson", side_effect=_fake_normalize):
        results = normalize_lessons_dir(src, out, Config(), use_cache=False)

    assert [r.resource_id for r in results] == codes
    progress = json.loads((out / "normalize_progress.json").read_text())
    assert progress["status"] == "complete"
    assert sorted(progress["completed"]) == codes


def test_normalize_lessons_dir_resume_skips_complete_output(tmp_path: Path):
    src, out = tmp_path / "lessons", tmp_path / "normalized"
    src.mkdir()
    codes = ["G1M2U1L1", "G1M2U1L2"]
    _write_lessons(src, codes)

    cfg = Config(normalize=NormalizeConfig(cache_dir=str(tmp_path / "cache")))
    lesson1 = _sample_lesson("G1M2U1L1")
    cache_key, *_ = _cache_plan(lesson1, cfg)
    cache = ContentAddressedCache(_resolve_cache_dir(cfg.normalize.cache_dir))
    cache.put(cache_key, _fake_normalize(lesson1, cfg))

    with patch(
        "veramynd_parser.normalize.lesson.normalize_lesson", side_effect=_fake_normalize
    ) as mocked:
        results = normalize_lessons_dir(src, out, cfg, use_cache=True)

    assert mocked.call_count == 1
    assert sorted(r.resource_id for r in results) == codes


def test_resume_recomputes_when_lesson_content_changed(tmp_path: Path):
    src, out = tmp_path / "lessons", tmp_path / "normalized"
    src.mkdir()
    cfg = Config(normalize=NormalizeConfig(cache_dir=str(tmp_path / "cache")))

    original = _sample_lesson("G1M2U1L1")
    cache_key, *_ = _cache_plan(original, cfg)
    cache = ContentAddressedCache(_resolve_cache_dir(cfg.normalize.cache_dir))
    cache.put(cache_key, _fake_normalize(original, cfg))

    edited = original.model_copy(update={"title": "Lesson 1: A Brand New Title"})
    (src / "G1M2U1L1.json").write_text(edited.model_dump_json(), encoding="utf-8")

    with patch(
        "veramynd_parser.normalize.lesson.normalize_lesson", side_effect=_fake_normalize
    ) as mocked:
        normalize_lessons_dir(src, out, cfg, use_cache=True)

    assert mocked.call_count == 1


def test_normalize_lessons_dir_sequential_raises_immediately_on_first_failure(tmp_path: Path):
    src, out = tmp_path / "lessons", tmp_path / "normalized"
    src.mkdir()
    codes = ["G1M2U1L1", "G1M2U1L2"]
    _write_lessons(src, codes)

    def _boom(lesson, cfg, use_cache=True, refresh_cache=False):
        if lesson.code == "G1M2U1L1":
            raise RuntimeError("simulated failure")
        return _fake_normalize(lesson, cfg, use_cache, refresh_cache)

    with patch("veramynd_parser.normalize.lesson.normalize_lesson", side_effect=_boom):
        with pytest.raises(RuntimeError, match="simulated failure"):
            normalize_lessons_dir(src, out, Config(), use_cache=False)

    progress = json.loads((out / "normalize_progress.json").read_text())
    assert progress["status"] == "interrupted"
    assert progress["failed"][0]["code"] == "G1M2U1L1"
    assert not (out / "G1M2U1L2.json").exists()


def test_normalize_lessons_dir_concurrent_matches_sequential_result(tmp_path: Path):
    src = tmp_path / "lessons"
    src.mkdir()
    codes = ["G1M2U1L1", "G1M2U1L2", "G1M2U1L3", "G1M2U1L4"]
    _write_lessons(src, codes)

    with patch("veramynd_parser.normalize.lesson.normalize_lesson", side_effect=_fake_normalize):
        seq_results = normalize_lessons_dir(
            src, tmp_path / "normalized_seq", Config(), use_cache=False, max_workers=1
        )
        par_results = normalize_lessons_dir(
            src, tmp_path / "normalized_par", Config(), use_cache=False, max_workers=4
        )

    assert [r.resource_id for r in seq_results] == [r.resource_id for r in par_results] == codes


def test_normalize_lessons_dir_concurrent_cancels_queue_after_failure(tmp_path: Path):
    import time

    src, out = tmp_path / "lessons", tmp_path / "normalized"
    src.mkdir()
    codes = [f"G1M2U1L{i}" for i in range(1, 9)]
    _write_lessons(src, codes)
    started: list[str] = []

    def _boom(lesson, cfg, use_cache=True, refresh_cache=False):
        started.append(lesson.code)
        if lesson.code == "G1M2U1L1":
            raise RuntimeError("simulated failure")
        time.sleep(0.05)
        return _fake_normalize(lesson, cfg, use_cache, refresh_cache)

    with patch("veramynd_parser.normalize.lesson.normalize_lesson", side_effect=_boom):
        with pytest.raises(RuntimeError, match="simulated failure"):
            normalize_lessons_dir(src, out, Config(), use_cache=False, max_workers=2)

    assert "G1M2U1L1" in started
    assert len(started) < len(codes)
    assert not (out / "G1M2U1L1.json").exists()
    progress = json.loads((out / "normalize_progress.json").read_text())
    assert progress["failed"][0]["code"] == "G1M2U1L1"
    assert progress["status"] == "interrupted"


def test_max_workers_below_one_rejected():
    with pytest.raises(ValueError):
        normalize_lessons_dir(Path("."), Path("."), Config(), max_workers=0)


def test_dump_matches_blank_template_keys():
    """Serialized record must carry blank-template fields; pipeline is nested."""
    from veramynd_parser.normalize.models import _ELA_TEMPLATE_KEYS

    dumped = dump_ela_record(minimal_normalized_lesson(prompt_version="normalize_ela.v1"))
    assert set(_ELA_TEMPLATE_KEYS).issubset(dumped.keys())
    assert "student_competencies" not in dumped
    assert "pedagogy_terms" not in dumped
    assert "instructional_text" not in dumped
    assert dumped["assessment"]["recognition_vs_production"] is None
    assert dumped["example_items"] == {}
    assert "text_complexity" not in dumped["subject_profile"]
    assert dumped["_pipeline"]["prompt_version"] == "normalize_ela.v1"

    roundtrip = parse_ela_record(dumped)
    assert roundtrip.resource_id == "G1M2U1L1"
    assert roundtrip.prompt_version == "normalize_ela.v1"


def test_evidence_coverage_rule_enforced():
    from pydantic import ValidationError

    with pytest.raises(ValidationError, match="missing coverage"):
        NormalizedLesson(
            resource_id="G1M2U1L1",
            title="t",
            domain=DomainBlock(primary="Speaking & Listening"),
            objective="o",
            what_is_taught=[
                TaughtSkill(
                    skill="talk",
                    cognitive_demand="DOK1_recall_reproduction",
                )
            ],
            student_actions=StudentActions(
                oral_production="Students talk.",
            ),
            evidence=[
                EvidenceItem(
                    quote="Teacher models.",
                    location="Opening",
                    actor="teacher",
                    evidence_role="teacher_model",
                    support="modeled",
                    supports_action=[],
                )
            ],
            teacher_actions=TeacherActions(with_prompting_and_support="no"),
            subject_profile=SubjectProfile(mode="interpretation", genre="n/a"),
        )
