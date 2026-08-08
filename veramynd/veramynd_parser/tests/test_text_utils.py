"""Unit tests for text_utils's standalone helpers."""

from __future__ import annotations

from pathlib import Path

from veramynd_parser import text_utils as tu


def test_dedupe_preserve_order_keeps_first_seen_order():
    assert tu.dedupe_preserve_order(["W.1.8", "SL.1.1", "SL.1.1a", "SL.1.2", "W.1.8"]) == [
        "W.1.8",
        "SL.1.1",
        "SL.1.1a",
        "SL.1.2",
    ]


def test_dedupe_preserve_order_empty():
    assert tu.dedupe_preserve_order([]) == []


def test_extract_standard_codes_preserves_source_order():
    """Regression: this used to be sorted(set(...)), alphabetizing away from the
    order codes actually appear in the source text."""
    text = "See W.1.8 and also SL.1.1, plus SL.1.1a and W.1.8 again."
    assert tu.extract_standard_codes(text) == ["W.1.8", "SL.1.1", "SL.1.1a"]


def test_extract_standard_codes_supports_kindergarten_and_longer_suffix():
    text = "See RL.K.1 and L.1.1fg in the guide."
    assert tu.extract_standard_codes(text) == ["RL.K.1", "L.1.1fg"]


def test_stitch_wrapped_standard_code_joins_grade_1():
    assert tu.stitch_wrapped_standard_code("RL.1.\n1") == "RL.1.1"


def test_stitch_wrapped_standard_code_supports_kindergarten_grade():
    """Regression: the wrap-stitcher only matched a digit grade segment, so a
    wrapped Kindergarten code ('RL.K.\\n1') was silently left un-stitched even
    though STANDARD_CODE itself (and extract_standard_codes) explicitly support
    the 'K' grade segment."""
    assert tu.stitch_wrapped_standard_code("RL.K.\n1") == "RL.K.1"


def test_stitch_wrapped_standard_code_supports_four_letter_prefix():
    """Regression: the wrap-stitcher capped the prefix at 3 letters while
    STANDARD_CODE allows up to 4 -- a wrapped 4-letter-prefix code would not be
    recognized as a standard code at all after a naive whitespace collapse."""
    assert tu.stitch_wrapped_standard_code("CCRA.1.\n1") == "CCRA.1.1"


def test_atomic_write_text_writes_content_and_leaves_no_temp_file(tmp_path: Path):
    dest = tmp_path / "out.json"
    tu.atomic_write_text(dest, "hello world")
    assert dest.read_text(encoding="utf-8") == "hello world"
    leftovers = [p for p in tmp_path.iterdir() if p != dest]
    assert leftovers == []


def test_atomic_write_text_overwrites_existing_file(tmp_path: Path):
    dest = tmp_path / "out.json"
    dest.write_text("old", encoding="utf-8")
    tu.atomic_write_text(dest, "new")
    assert dest.read_text(encoding="utf-8") == "new"


def test_atomic_replace_dir_swaps_without_empty_window(tmp_path: Path):
    src = tmp_path / "new_lessons"
    dest = tmp_path / "lessons"
    src.mkdir()
    dest.mkdir()
    (src / "a.json").write_text("new", encoding="utf-8")
    (dest / "old.json").write_text("old", encoding="utf-8")

    tu.atomic_replace_dir(src, dest)

    assert (dest / "a.json").read_text(encoding="utf-8") == "new"
    assert not (dest / "old.json").exists()
    leftovers = [p.name for p in tmp_path.iterdir() if p.name.startswith(".")]
    assert leftovers == []


def test_strip_trailing_codes_handles_k_grades():
    """Regression: the split pattern missed 'RL.K' and split on the inner 'K.1',
    leaving a stranded '(RL.' fragment on every kindergarten target."""
    from veramynd_parser.text_utils import strip_trailing_codes

    assert (
        strip_trailing_codes("I can describe characters. (RL.K.1)")
        == "I can describe characters."
    )
    assert (
        strip_trailing_codes("I can describe what I observe. (W.1.8, SL.1.1)")
        == "I can describe what I observe."
    )


def test_dehyphenate_preserves_compounds_seen_elsewhere():
    """A wrap at a real compound's hyphen keeps it when the unwrapped form
    appears elsewhere in the same text; plain soft wraps still join."""
    from veramynd_parser.text_utils import dehyphenate

    text = "Begin the read-\naloud now. Yesterday's read-aloud went well."
    assert "read-aloud now" in dehyphenate(text)
    assert dehyphenate("Count the min-\nutes carefully.") == "Count the minutes carefully."


def test_dehyphenate_preserves_a_wrapped_numeric_range():
    """Regression: a page-range citation wrapped at the hyphen ('42-\\n43')
    was silently merged into a different number ('4243') by the same
    no-evidence-found fallback meant for compound words."""
    from veramynd_parser.text_utils import dehyphenate

    assert dehyphenate("See pages 42-\n43 for details.") == "See pages 42-43 for details."
