"""Separation tests — the document must split into exactly the right lessons."""

from __future__ import annotations


def test_lesson_count(guide):
    assert len(guide.lessons) == 40


def test_unit_distribution(guide):
    counts = {u.unit: len(u.lessons) for u in guide.units}
    assert counts == {1: 15, 2: 12, 3: 13}


def test_grade_and_module_from_document(guide):
    # read from the bookmark codes, not hardcoded
    assert guide.grade == 1
    assert guide.module == 2


def test_codes_are_unique(guide):
    codes = [lesson.code for lesson in guide.lessons]
    assert len(set(codes)) == len(codes)


def test_codes_are_well_formed(guide):
    import re

    for lesson in guide.lessons:
        assert re.fullmatch(r"G1M2U\dL\d+", lesson.code), lesson.code


def test_pages_partition_without_gaps_or_overlaps(guide):
    covered: set[int] = set()
    for u in guide.units:
        if u.overview_page_start and u.overview_page_end:
            covered |= set(range(u.overview_page_start, u.overview_page_end + 1))
    for lesson in guide.lessons:
        rng = set(range(lesson.page_start, lesson.page_end + 1))
        assert not (covered & rng), f"overlap at {lesson.code}"
        covered |= rng
    assert covered == set(range(1, guide.page_count + 1))


def test_lessons_contiguous_within_unit(guide):
    for u in guide.units:
        for a, b in zip(u.lessons, u.lessons[1:]):
            assert a.page_end + 1 == b.page_start


def test_first_lesson_boundaries(guide):
    first = guide.lessons[0]
    assert first.code == "G1M2U1L1"
    assert (first.page_start, first.page_end) == (12, 23)
