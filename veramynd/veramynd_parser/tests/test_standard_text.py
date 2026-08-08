"""Tests for enterprise leaf retrieval text (no embed_text duplication)."""

from __future__ import annotations

from veramynd_parser.embed.standard_text import build_retrieval_text


def test_build_retrieval_text_rich_fields_and_no_duplicate_embed():
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
        "student_actions": {
            "oral_production": "use new vocabulary when discussing texts",
            "recognition_identification": "NONE OBSERVED",
        },
        # Already a line of the rich text — must not be appended a second time.
        "embed_text": "Standard: 1.L.V.1.a",
    }
    text = build_retrieval_text(data)
    assert text.startswith("Standard: 1.L.V.1.a")
    assert "Domain primary: Vocabulary" in text
    assert "Domain secondary: Language" in text
    assert "Competency:" in text
    assert "Official text:" in text
    assert "Skills:" in text
    assert "Observable behaviors:" in text
    assert "Pedagogy terms / keywords:" in text
    assert "Required student actions:" in text
    assert "- oral_production: use new vocabulary when discussing texts" in text
    assert "NONE OBSERVED" not in text
    assert text.count("Standard: 1.L.V.1.a") == 1


def test_build_retrieval_text_falls_back_to_embed_when_empty_fields():
    text = build_retrieval_text(
        {
            "standard_code": "",
            "embed_text": "Fallback retrieval blob about syllables.",
        }
    )
    assert "Fallback retrieval blob" in text
