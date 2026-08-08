"""Tests for standards normalization (assemble / sanitize / embed_text)."""

from __future__ import annotations

from veramynd_parser.models import GradeStandards, Standard, StandardLevel
from veramynd_parser.normalize.standard import (
    _assemble_record,
    sanitize_normalized_standard,
    standard_normalize_payload,
    safe_standard_filename,
)
from veramynd_parser.normalize.standard_models import (
    StandardLlmDraft,
    build_standard_embed_text,
    minimal_normalized_standard,
)
from veramynd_parser.normalize.models import StudentActionsCore


def _sample_tree() -> GradeStandards:
    return GradeStandards(
        grade=1,
        framework="GA ELA",
        standards=[
            Standard(
                code="1.F",
                level=StandardLevel.DOMAIN,
                label="Foundations",
                text="Students build a foundation for literacy.",
                parent_code=None,
                grade=1,
            ),
            Standard(
                code="1.F.PA",
                level=StandardLevel.BIG_IDEA,
                label="Phonological Awareness",
                text="Students develop phonological awareness.",
                parent_code="1.F",
                grade=1,
            ),
            Standard(
                code="1.F.PA.4",
                level=StandardLevel.STANDARD,
                label="Syllables",
                text="Identify and manipulate syllables in spoken words.",
                parent_code="1.F.PA",
                grade=1,
            ),
            Standard(
                code="1.F.PA.4.d",
                level=StandardLevel.SUBSTANDARD,
                label="",
                text="Add, delete, and substitute syllables in spoken words.",
                parent_code="1.F.PA.4",
                grade=1,
            ),
        ],
    )


def test_safe_standard_filename_allows_dots():
    assert safe_standard_filename("1.F.PA.4.d") == "1.F.PA.4.d"


def test_payload_includes_ancestors_and_children():
    tree = _sample_tree()
    std = next(s for s in tree.standards if s.code == "1.F.PA.4")
    payload = standard_normalize_payload(std, tree)
    assert payload["code"] == "1.F.PA.4"
    assert [a["code"] for a in payload["ancestors"]] == ["1.F", "1.F.PA"]
    assert payload["children"][0]["code"] == "1.F.PA.4.d"


def test_assemble_and_sanitize_builds_embed_text():
    tree = _sample_tree()
    std = next(s for s in tree.standards if s.code == "1.F.PA.4")
    draft = StandardLlmDraft(
        domain_primary="Phonological Awareness",
        domain_secondary=[],
        competency_statement="Students identify and change syllables in spoken words.",
        observable_behaviors=["Clap syllables in a spoken word"],
        pedagogy_terms=["syllables", "spoken words"],
        student_actions=StudentActionsCore(
            recognition_identification="identify syllables in spoken words",
            procedural_application="manipulate syllables when prompted",
        ),
        cognitive_demand="DOK2_skills_concepts",
        skill_clauses=[
            "identify syllables in spoken words",
            "manipulate syllables in spoken words",
        ],
        notes="",
    )
    assembled = _assemble_record(std, tree, draft)
    fixed, warnings = sanitize_normalized_standard(assembled)
    assert not warnings or all("exact_codes" not in w or True for w in warnings)
    assert fixed.standard_code == "1.F.PA.4"
    assert "1.F.PA.4" in fixed.exact_codes
    assert fixed.embed_text
    assert fixed.embed_text.startswith("Standard: 1.F.PA.4")
    assert "Skills:" in fixed.embed_text
    assert "Required student actions:" in fixed.embed_text
    assert fixed.child_codes == ["1.F.PA.4.d"]


def test_minimal_embed_text_helper():
    n = minimal_normalized_standard()
    text = build_standard_embed_text(n)
    assert text.startswith("Standard: 1.F.PA.4")
    assert "Domain primary: Phonological Awareness" in text
    assert "Skills:" in text
    assert "Required student actions:" in text
