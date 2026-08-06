"""Tests for enterprise leaf retrieval text (no embed_text duplication)."""

from __future__ import annotations

from veramynd_parser.embed.standard_text import build_retrieval_text


def test_build_retrieval_text_students_can_and_no_duplicate_embed():
    data = {
        "standard_code": "1.L.V.1.a",
        "domain": {"primary": "Vocabulary", "secondary": ["Language"]},
        "competency_statement": (
            "Use general, academic, and specialized vocabulary from grade-level texts."
        ),
        "raw_text": "Acquire and apply vocabulary words and phrases. (I)",
        "skill_clauses": [
            "Acquire vocabulary words and phrases through grade-level texts.",
            "Apply vocabulary words and phrases in appropriate contexts.",
        ],
        "observable_behaviors": [
            "Identify and use vocabulary words from texts.",
            "Apply new words when speaking and writing.",
        ],
        "pedagogy_terms": ["vocabulary", "academic vocabulary", "word meaning"],
        "verbs": ["acquire", "apply"],
        "concepts": ["word meaning", "context"],
        "instructional_intent": "Transfer vocabulary knowledge into communication.",
        "normalized_keywords": ["context clues"],
        "student_actions": {
            "oral_production": "use new vocabulary when discussing texts",
            "recognition_identification": "NONE OBSERVED",
        },
        "embed_text": (
            "Standard: 1.L.V.1.a\n"
            "Domain primary: Vocabulary\n"
            "Competency: Use general, academic, and specialized vocabulary "
            "from grade-level texts."
        ),
    }
    text = build_retrieval_text(data)
    assert "Students can:" in text
    assert "Skill focus:" in text
    assert "Required verbs:" in text
    assert "Concepts:" in text
    assert "Instructional intent:" in text
    assert "Normalized keywords:" in text
    assert "In the classroom, students:" in text
    assert text.count("Students can:") == 1
    assert "Competency:" not in text
    assert "vocabulary" in text.lower()


def test_build_retrieval_text_falls_back_to_embed_when_empty_fields():
    text = build_retrieval_text(
        {
            "standard_code": "",
            "embed_text": "Fallback retrieval blob about syllables.",
        }
    )
    assert "Fallback retrieval blob" in text
