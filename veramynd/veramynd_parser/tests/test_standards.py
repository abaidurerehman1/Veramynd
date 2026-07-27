"""Standards-tree tests — the flat spreadsheet becomes the right hierarchy."""

from __future__ import annotations

from veramynd_parser.models import StandardLevel
from veramynd_parser.standards.spreadsheet import level_of, parent_of


def test_row_count(standards):
    assert len(standards.standards) == 188


def test_grade_read_from_codes(standards):
    assert standards.grade == 1


def test_level_distribution(standards):
    counts = {level: len(standards.by_level(level)) for level in StandardLevel}
    assert counts == {
        StandardLevel.DOMAIN: 4,
        StandardLevel.BIG_IDEA: 14,
        StandardLevel.STANDARD: 35,
        StandardLevel.SUBSTANDARD: 135,
    }


def test_level_is_derived_from_code_depth_not_notes():
    assert level_of("1.F") is StandardLevel.DOMAIN
    assert level_of("1.F.PA") is StandardLevel.BIG_IDEA
    assert level_of("1.F.PA.4") is StandardLevel.STANDARD
    assert level_of("1.F.PA.4.d") is StandardLevel.SUBSTANDARD


def test_parent_links():
    assert parent_of("1.F.PA.4.d") == "1.F.PA.4"
    assert parent_of("1.F.PA.4") == "1.F.PA"
    assert parent_of("1.F.PA") == "1.F"
    assert parent_of("1.F") is None


def test_every_child_has_a_present_parent(standards):
    codes = {s.code for s in standards.standards}
    for s in standards.standards:
        if s.parent_code is not None:
            assert s.parent_code in codes, f"orphan: {s.code}"


def test_domains_are_the_four_expected(standards):
    domains = {s.code for s in standards.by_level(StandardLevel.DOMAIN)}
    assert domains == {"1.F", "1.P", "1.L", "1.T"}


def test_label_split(standards):
    # e.g. "Syllables: Identify and manipulate..." -> label "Syllables"
    syl = next((s for s in standards.standards if s.code == "1.F.PA.4"), None)
    if syl is not None:
        assert syl.label  # a short prefix label was extracted
