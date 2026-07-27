"""Domain-model validation tests — invalid data must be rejected at construction,
not silently accepted and only maybe caught later by the verifier."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from veramynd_parser.models import AgendaItem, InstructionalBlock, LearningTarget, Lesson


def _lesson_kwargs(**overrides) -> dict:
    base = dict(
        code="G1M2U1L1",
        grade=1,
        module=2,
        unit=1,
        lesson=1,
        page_start=12,
        page_end=23,
    )
    base.update(overrides)
    return base


def test_valid_lesson_constructs():
    Lesson(**_lesson_kwargs())


def test_negative_grade_rejected():
    with pytest.raises(ValidationError):
        Lesson(**_lesson_kwargs(grade=-1))


def test_page_start_below_one_rejected():
    with pytest.raises(ValidationError):
        Lesson(**_lesson_kwargs(page_start=0))


def test_declared_standards_malformed_code_rejected():
    with pytest.raises(ValidationError):
        Lesson(**_lesson_kwargs(declared_standards=["not-a-code"]))


def test_declared_standards_well_formed_code_accepted():
    lesson = Lesson(**_lesson_kwargs(declared_standards=["RL.1.1", "SL.1.1a"]))
    assert lesson.declared_standards == ["RL.1.1", "SL.1.1a"]


def test_learning_target_malformed_code_rejected():
    with pytest.raises(ValidationError):
        LearningTarget(text="I can read.", codes=["garbage"])


def test_agenda_item_letter_must_be_single_uppercase():
    AgendaItem(section="Opening", letter="A", title="X", minutes=10)
    with pytest.raises(ValidationError):
        AgendaItem(section="Opening", letter="a", title="X", minutes=10)
    with pytest.raises(ValidationError):
        AgendaItem(section="Opening", letter="AB", title="X", minutes=10)


def test_instructional_block_page_zero_sentinel_is_valid():
    """0 is the documented 'unmatched' sentinel — must remain constructible."""
    block = InstructionalBlock(section="Opening", letter="A", title="X", page=0, steps=[])
    assert block.page == 0


def test_instructional_block_negative_page_rejected():
    with pytest.raises(ValidationError):
        InstructionalBlock(section="Opening", letter="A", title="X", page=-1, steps=[])


def test_instructional_block_letter_must_be_single_uppercase():
    with pytest.raises(ValidationError):
        InstructionalBlock(section="Opening", letter="1", title="X", page=1, steps=[])


def test_lesson_code_mismatch_with_fields_rejected():
    """Pre-existing invariant (models.py _check_invariants) — codified here
    alongside the newer field-level constraints for one place to look."""
    with pytest.raises(ValidationError):
        Lesson(**_lesson_kwargs(code="G1M2U1L2"))  # code says L2, lesson field says 1
