"""Division tests — each lesson splits into the right parts."""

from __future__ import annotations

import pytest


def _lesson(guide, code):
    return next(l for l in guide.lessons if l.code == code)


def test_title_is_complete(guide):
    first = _lesson(guide, "G1M2U1L1")
    assert first.title.startswith("Lesson 1: Noticing and Wondering")
    assert first.title.endswith("Sun, Moon, and Stars")


def test_declared_standards_preserve_source_order(guide):
    """Regression: declared_standards used to be alphabetized (sorted(set(...))),
    silently reordering away from the publisher's own listing. The guide lists
    W.1.8 first here, not SL.1.1 -- confirmed against the raw PDF text."""
    first = _lesson(guide, "G1M2U1L1")
    assert first.declared_standards == ["W.1.8", "SL.1.1", "SL.1.1a", "SL.1.2"]


def test_learning_targets_are_tagged(guide):
    first = _lesson(guide, "G1M2U1L1")
    assert len(first.learning_targets) == 2
    for target in first.learning_targets:
        assert target.text.startswith("I can")
        assert target.codes  # every target carries at least one standard code


def test_agenda_blocks_and_timing(guide):
    first = _lesson(guide, "G1M2U1L1")
    assert len(first.agenda) == 6
    assert first.total_minutes == 60
    sections = {a.section for a in first.agenda}
    assert sections == {"Opening", "Work Time", "Closing and Assessment"}


def test_instructional_blocks_present_everywhere(guide):
    for lesson in guide.lessons:
        sections = {b.section for b in lesson.instructional_blocks}
        assert {"Opening", "Work Time", "Closing and Assessment"} <= sections, lesson.code


def test_instructional_blocks_carry_steps(guide):
    """Every sub-block must carry its instructional steps — the content, not just a label."""
    for lesson in guide.lessons:
        assert lesson.instructional_blocks, lesson.code
        for block in lesson.instructional_blocks:
            assert block.steps, f"{lesson.code} {block.section} {block.letter} has no steps"


def test_agenda_plan_matches_body_blocks(guide):
    """The cover agenda (plan) and the body sub-blocks (execution) must line up 1:1."""
    for lesson in guide.lessons:
        assert len(lesson.agenda) == len(lesson.instructional_blocks), lesson.code


def test_work_time_c_not_merged_into_b(guide):
    """Regression: G1M2U1L2's Work Time C was mislabeled and merged into B."""
    l2 = _lesson(guide, "G1M2U1L2")
    wt = [b for b in l2.instructional_blocks if b.section == "Work Time"]
    letters = {b.letter for b in wt}
    assert {"A", "B", "C"} <= letters
    wtc = next(b for b in wt if b.letter == "C")
    assert wtc.title.startswith("Independent Writing")
    assert wtc.steps


def test_every_agenda_is_in_a_sane_band(guide):
    """The de-hyphenation + minutes-stitching fixes must hold for all 40 lessons."""
    for lesson in guide.lessons:
        total = lesson.total_minutes
        assert total is not None, f"{lesson.code} has no agenda timing"
        assert 45 <= total <= 75, f"{lesson.code} = {total} min (out of band)"


def test_singular_daily_learning_target_is_parsed(guide):
    """L5 uses the singular header 'Daily Learning Target' (one target)."""
    l5 = _lesson(guide, "G1M2U1L5")
    assert len(l5.learning_targets) == 1
    assert l5.learning_targets[0].codes  # its tagged codes were captured


@pytest.mark.parametrize("code", ["G1M2U1L9", "G1M2U2L6", "G1M2U3L10"])
def test_wrapped_minutes_are_recovered(guide, code):
    """Lessons whose agenda durations word-wrapped must still total in-band."""
    lesson = _lesson(guide, code)
    assert 45 <= (lesson.total_minutes or 0) <= 75
