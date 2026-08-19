"""The two per-engine dividers must share the same structural contract.

Regression guard for the inverted-dependency fix: fill_steps() used to live inside
docling_divider.py, so the PyMuPDF ("fallback") divider imported from the Docling
("primary") one for logic that isn't Docling-specific at all. It now lives in the
neutral pdf/division.py module that both import from — this pins that down and
also catches future drift between the two divider classes' public surface.
"""

from __future__ import annotations

from types import SimpleNamespace

from veramynd_parser.models import InstructionalBlock
from veramynd_parser.pdf.division import LessonDivider, fill_steps
from veramynd_parser.pdf.divider import _Divider
from veramynd_parser.pdf.docling_divider import _DoclingDivider


def test_neither_divider_module_defines_its_own_fill_steps():
    import veramynd_parser.pdf.divider as divider_mod
    import veramynd_parser.pdf.docling_divider as docling_divider_mod

    assert not hasattr(divider_mod, "_fill_steps")
    assert not hasattr(docling_divider_mod, "_fill_steps")
    assert fill_steps is divider_mod.fill_steps
    assert fill_steps is docling_divider_mod.fill_steps


def test_both_dividers_implement_the_same_contract():
    required = {name for name in dir(LessonDivider) if not name.startswith("_")}
    assert required  # sanity: the Protocol actually declares something
    assert required <= set(dir(_Divider))
    assert required <= set(dir(_DoclingDivider))


def test_fill_steps_distinguishes_titles_that_share_a_14_char_prefix():
    """Regression: truncating match keys to 14 chars collided on titles like
    'Unit 2 Assessment, Group 1/2' and mis-attached Group 2 steps under Group 1.

    Matching uses longest shared prefix (min length) so Group 1 vs Group 2 still
    disambiguate while truncated body headers can still match.
    """
    cfg = SimpleNamespace(
        instructional_sections=("Opening", "Work Time", "Closing and Assessment")
    )
    blocks = [
        InstructionalBlock(
            section="Work Time",
            letter="A",
            title="Unit 2 Assessment, Group 1: Science Talk",
            minutes=20,
            page=0,
            steps=[],
        ),
        InstructionalBlock(
            section="Work Time",
            letter="B",
            title="Unit 2 Assessment, Group 2: Science Talk",
            minutes=20,
            page=0,
            steps=[],
        ),
    ]
    body = [
        ("section_header", "Work Time", 10),
        ("section_header", "A. Unit 2 Assessment, Group 1: Science Talk (20 minutes)", 10),
        ("list_item", "Group 1 discusses patterns.", 10),
        ("list_item", "Record Group 1 notes.", 10),
        ("section_header", "B. Unit 2 Assessment, Group 2: Science Talk (20 minutes)", 11),
        ("list_item", "Group 2 discusses patterns.", 11),
        ("list_item", "Record Group 2 notes.", 11),
    ]
    filled = fill_steps(blocks, body, cfg)
    assert filled[0].page == 10
    assert filled[1].page == 11
    assert filled[0].step_texts == [
        "Group 1 discusses patterns.",
        "Record Group 1 notes.",
    ]
    assert filled[1].step_texts == [
        "Group 2 discusses patterns.",
        "Record Group 2 notes.",
    ]


def test_fill_steps_ignores_a_coincidental_prefix_match_in_ordinary_prose():
    """Regression: real bug found in G1M2U2L5 of the reference document. An
    ordinary body sentence ("...use the shared writing.") normalized to
    'sharedwriting', which is a complete 13-char prefix of a LATER block's key
    ('sharedwritingdescribingthepositionofthesun') -- past MIN_PREFIX (12).
    Because that candidate was an ordinary list_item, not a detected header, the
    fuzzy match used to fire anyway: it skipped an entire intervening block
    (which then never matched at all) and silently merged that block's real
    steps plus the skipped block's real steps into the wrong (later) block --
    with every block still ending up with >=1 step, so no verifier check other
    than the skipped block's own page==0 caught any of it. Fuzzy matching must
    only fire on candidates already labeled section_header; ordinary prose must
    never be treated as a candidate header, no matter how long its shared
    prefix with an upcoming title happens to be.
    """
    cfg = SimpleNamespace(
        instructional_sections=("Opening", "Work Time", "Closing and Assessment")
    )
    blocks = [
        InstructionalBlock(
            section="Work Time", letter="C",
            title="Shared Writing: Reflecting on Unit 2 Guiding Question",
            minutes=10, page=0, steps=[],
        ),
        InstructionalBlock(
            section="Closing and Assessment", letter="A",
            title="Independent Writing: Sky Notebook",
            minutes=10, page=0, steps=[],
        ),
        InstructionalBlock(
            section="Closing and Assessment", letter="B",
            title="Shared Writing: Describing the Position of the Sun",
            minutes=5, page=0, steps=[],
        ),
    ]
    body = [
        ("section_header", "Work Time", 232),
        ("section_header", "C. Shared Writing: Reflecting on Unit 2 Guiding Question (10 minutes)", 232),
        ("list_item", "Tell students they will have a chance to help add to the anchor chart using", 232),
        # This is the exact fragment (its own line in the source PDF) that triggered
        # the false positive: normalized, it is a bare prefix ("sharedwriting") of
        # Closing B's key ("sharedwritingdescribingthepositionofthesun") -- 13 shared
        # characters, at MIN_PREFIX. It must not be mistaken for that block's header.
        ("list_item", "shared writing.", 232),
        ("section_header", "Closing and Assessment", 233),
        ("section_header", "A. Independent Writing: Sky Notebook (10 minutes)", 233),
        ("list_item", "Refocus students whole group.", 233),
        ("section_header", "Closing and Assessment", 234),
        ("section_header", "B. Shared Writing: Describing the Position of the Sun (5 minutes)", 234),
        ("list_item", "Display the recording form.", 234),
    ]
    filled = fill_steps(blocks, body, cfg)
    work_time_c, closing_a, closing_b = filled
    assert work_time_c.page == 232
    assert work_time_c.step_texts == [
        "Tell students they will have a chance to help add to the anchor chart using",
        "shared writing.",
    ]
    assert closing_a.page == 233
    assert closing_a.step_texts == ["Refocus students whole group."]
    assert closing_b.page == 234
    assert closing_b.step_texts == ["Display the recording form."]


def test_fill_steps_matches_truncated_body_header_via_shared_prefix():
    """Body headers shorter than the agenda title must still attach (shared prefix)."""
    cfg = SimpleNamespace(
        instructional_sections=("Opening", "Work Time", "Closing and Assessment")
    )
    blocks = [
        InstructionalBlock(
            section="Opening",
            letter="A",
            title="Song and Movement: 'Sun, Moon, and Stars' Song",
            minutes=5,
            page=0,
            steps=[],
        ),
    ]
    body = [
        ("section_header", "Opening", 2),
        # truncated vs full agenda title — still shares a long alphanumeric prefix
        ("section_header", "A. Song and Movement: 'Sun, Moon, and Stars'", 2),
        ("list_item", "Students sing.", 2),
    ]
    filled = fill_steps(blocks, body, cfg)
    assert filled[0].page == 2
    assert filled[0].step_texts == ["Students sing."]


def test_fill_steps_keeps_each_line_on_the_page_it_came_from():
    """A block that continues across a page break must not collapse to the start page."""
    cfg = SimpleNamespace(
        instructional_sections=("Opening", "Work Time", "Closing and Assessment")
    )
    blocks = [
        InstructionalBlock(
            section="Work Time",
            letter="A",
            title="Close Read",
            minutes=15,
            page=0,
            steps=[],
        ),
    ]
    page_45 = [f"Step on page 45 number {i}." for i in range(1, 21)]
    page_46 = [f"Step on page 46 number {i}." for i in range(1, 11)]
    body = [
        ("section_header", "Work Time", 45),
        ("section_header", "A. Close Read (15 minutes)", 45),
        *(("list_item", line, 45) for line in page_45),
        *(("list_item", line, 46) for line in page_46),
    ]
    filled = fill_steps(blocks, body, cfg)
    assert filled[0].page == 45
    pages = [s.page for s in filled[0].steps]
    assert pages[:20] == [45] * 20
    assert pages[20:] == [46] * 10
