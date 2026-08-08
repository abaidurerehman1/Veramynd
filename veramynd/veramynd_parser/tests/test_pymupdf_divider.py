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


# ---- Synthetic dehyphenation regressions (no PDF needed) -------------------


def _make_divider(lines_with_tiers):
    """Build a _Divider with hand-picked (text, tier) lines, bypassing font
    classification entirely — these tests pin the join logic, not tiering."""
    from veramynd_parser.config import Config
    from veramynd_parser.fonts import Span
    from veramynd_parser.pdf.divider import _Divider
    from veramynd_parser.pdf.document import Line

    d = object.__new__(_Divider)
    d.cfg = Config()
    d.lines = [
        Line(page=1, text=text, head=Span(text=text, font="Body", size=10.0))
        for text, _tier in lines_with_tiers
    ]
    d.tiers = [tier for _text, tier in lines_with_tiers]
    return d


def test_title_dehyphenates_a_line_wrapped_word():
    """Regression: a title spanning two physical lines with a soft-hyphen wrap
    ('Ques-' / 'tions') was joined with a bare space, leaving 'Ques- tions'
    in the parsed lesson title."""
    from veramynd_parser.fonts import TIER_MAJOR

    d = _make_divider(
        [
            ("Lesson 1: Noticing and Wondering: Observing and Asking Ques-", TIER_MAJOR),
            ("tions about the Sun, Moon, and Stars", TIER_MAJOR),
            ("Opening", TIER_MAJOR),
        ]
    )
    assert d.title() == (
        "Lesson 1: Noticing and Wondering: Observing and Asking Questions "
        "about the Sun, Moon, and Stars"
    )


def test_section_body_dehyphenates_a_wrapped_bullet_inside_parens():
    """Regression: a Materials bullet wrapped mid-word inside an open paren
    ('sup-' / 'porting materials)') merged via the existing continuation rule
    but with a bare space, leaving 'sup- porting' in the parsed entry."""
    from veramynd_parser.fonts import TIER_BODY, TIER_MAJOR, TIER_SECTION

    d = _make_divider(
        [
            ("Materials", TIER_SECTION),
            ("Patterns of the Sun anchor chart (new; co-created with students; see sup-", TIER_BODY),
            ("porting materials)", TIER_BODY),
            ("Opening", TIER_MAJOR),
        ]
    )
    assert d._section_body("Materials") == [
        "Patterns of the Sun anchor chart (new; co-created with students; see "
        "supporting materials)"
    ]


def test_section_body_still_space_joins_a_non_hyphenated_wrap():
    """Regression guard: fixing the hyphen case must not leave a raw '\\n' in
    an ordinary (non-hyphenated) paren-continuation wrap."""
    from veramynd_parser.fonts import TIER_BODY, TIER_MAJOR, TIER_SECTION

    d = _make_divider(
        [
            ("Materials", TIER_SECTION),
            ("Sun, Moon, and Stars Word Wall (begun in Lesson 1; added to; see", TIER_BODY),
            ("Teaching Notes)", TIER_BODY),
            ("Opening", TIER_MAJOR),
        ]
    )
    result = d._section_body("Materials")
    assert result == [
        "Sun, Moon, and Stars Word Wall (begun in Lesson 1; added to; see Teaching Notes)"
    ]
    assert "\n" not in result[0]


def test_instructional_block_step_merges_a_hyphen_wrapped_continuation():
    """Regression: a step's mid-word line-wrap ('Story Ele-' / 'ments board')
    became two separate entries in InstructionalBlock.steps instead of one
    dehyphenated step."""
    from veramynd_parser.fonts import TIER_BODY, TIER_MAJOR, TIER_RUNIN
    from veramynd_parser.models import AgendaItem

    d = _make_divider(
        [
            ("Opening", TIER_MAJOR),
            ("A. Shared writing", TIER_RUNIN),  # advances fill_steps to this block
            ("Point to the Story Ele-", TIER_BODY),
            ("ments board and name each icon.", TIER_BODY),
        ]
    )
    d.agenda = lambda: [
        AgendaItem(section="Opening", letter="A", title="Shared writing", minutes=10)
    ]
    blocks = d.instructional_blocks()
    assert len(blocks) == 1
    assert blocks[0].steps == ["Point to the Story Elements board and name each icon."]
