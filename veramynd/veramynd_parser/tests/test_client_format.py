"""Client correlation DOCX/XLSX + skill-named parent roll-up."""

from __future__ import annotations

from veramynd_parser.report.client_format import (
    build_parent_rollups,
    skill_phrase,
)


def test_skill_phrase_strips_ic_tag_and_lowercases():
    assert skill_phrase(
        "Make and track predictions about the events and information likely to come next. (I)"
    ).startswith("make and track predictions")


def test_parent_rollup_uses_skills_not_letters():
    standards = [
        {
            "level": "standard",
            "code": "1.P.EICC.3",
            "label": "Comprehension Strategies",
            "text": "Apply comprehension strategies.",
        },
        {
            "level": "substandard",
            "code": "1.P.EICC.3.d",
            "parent_code": "1.P.EICC.3",
            "text": "Summarize and visualize sections of the text to maintain understanding. (I)",
        },
        {
            "level": "substandard",
            "code": "1.P.EICC.3.f",
            "parent_code": "1.P.EICC.3",
            "text": "Make, track, and support inferences about different levels of meaning within the text. (I)",
        },
    ]
    teacher = {
        "1.P.EICC.3.d": {
            "pages": {44},
            "full_n": 1,
            "partial_n": 0,
            "lessons": {"G1M2U1L1"},
            "caveats": set(),
            "missing_page_lessons": set(),
            "partial_rationales": [],
        }
    }
    rollups = build_parent_rollups(standards, teacher)
    r = rollups["1.P.EICC.3"]
    assert r["alignment"] == "partially_met"
    stmt = r["statement"]
    assert stmt.startswith("This standard is partially met.")
    assert "summarize and visualize" in stmt.lower()
    assert "inferences" in stmt.lower()
    assert "does not yet address" not in stmt
    assert "fully covers" not in stmt
    assert "substandard(s)" not in stmt
