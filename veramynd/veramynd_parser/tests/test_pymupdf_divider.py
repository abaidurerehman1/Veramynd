"""PyMuPDF divider — page-furniture and line-wrap regressions.

Regression target: Materials/Vocabulary sections that span a page break picked up
running-header/footer noise (bare page numbers, the running header, the
'EL Education Curriculum N' footer signature) whenever that furniture happened to
render at body/run-in font size instead of the tier-2 size the code assumed all
page furniture used. Separately, a single bulleted item that PDF-wrapped across
two physical lines was emitted as two separate materials/vocabulary entries.

These only need PyMuPDF (no Docling), so — unlike test_docling.py, which is
skipped whole-file without Docling — they actually run in a lite (`pip install
.[lite]`) environment as long as the reference PDF is present.
"""

from __future__ import annotations

from veramynd_parser import text_utils as tu


def test_is_page_furniture_matches_known_noise_patterns():
    assert tu.is_page_furniture("66")
    assert tu.is_page_furniture("170")
    assert tu.is_page_furniture("Grade 1: Module 2: Unit 1: Lesson 8")
    assert tu.is_page_furniture("Unit 1: Lesson 3")
    assert tu.is_page_furniture("EL Education Curriculum 117")


def test_is_prep_or_tip_noise_matches_in_advance_bullets():
    assert tu.is_prep_or_tip_noise("Post: Learning target and applicable anchor charts.")
    assert tu.is_prep_or_tip_noise("-Sun Movement routine (see Lesson 2).")
    assert tu.is_prep_or_tip_noise(
        "During Work Time A, circulate and listen for students to use descriptive language."
    )
    assert not tu.is_prep_or_tip_noise("Pencils (one per student)")
    assert not tu.is_prep_or_tip_noise("respect (L)")


def test_is_page_furniture_does_not_match_real_content():
    assert not tu.is_page_furniture("Pencils (one per student)")
    assert not tu.is_page_furniture("sun, moon, stars (L)")
    assert not tu.is_page_furniture(
        "Sun, Moon, and Stars Word Wall cards (new; teacher-created; two)"
    )
    # A number embedded in real content, not standing alone, must not match.
    assert not tu.is_page_furniture("Crayons (class set; 24 colors per student)")


def test_no_page_furniture_leaks_into_materials_or_vocabulary(guide_pymupdf):
    leaks = [
        (lesson.code, item)
        for lesson in guide_pymupdf.lessons
        for item in lesson.materials + lesson.vocabulary
        if tu.is_page_furniture(item)
    ]
    assert not leaks, leaks


def test_wrapped_materials_bullet_is_not_split_into_two_entries(guide_pymupdf):
    """G1M2U1L3's Materials list has a bullet that PDF-wraps across two physical
    lines ('...added to in Work Time B; see' / 'Teaching Notes)') — it must come
    back as one entry, not two orphaned fragments."""
    l3 = next(l for l in guide_pymupdf.lessons if l.code == "G1M2U1L3")
    assert not any(m.rstrip().endswith("see") for m in l3.materials)
    assert not any(m.strip() == "Teaching Notes)" for m in l3.materials)
    assert any("Word Wall (begun in Lesson 1; added to in Work Time B; see Teaching Notes)" in m
               for m in l3.materials)


def test_g1m2u1l1_vocabulary_matches_docling_reference(guide_pymupdf):
    """Preserve New vs Review from the source: observe/effective are Review."""
    l1 = next(l for l in guide_pymupdf.lessons if l.code == "G1M2U1L1")
    assert l1.vocabulary == [
        "sun, moon, stars (L)",
        "Review: observe, effective (L)",
    ]
