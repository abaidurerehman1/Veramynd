"""Tests for the non-hardcoded crosswalk tooling in scripts_standalone/.

scripts_standalone/ sits outside the veramynd_parser package (it's ad-hoc
tooling, not shipped application code) so it has no __init__.py -- import it
by inserting its directory onto sys.path, same way it was exercised manually
while building it.
"""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts_standalone"
sys.path.insert(0, str(SCRIPTS_DIR))

import apply_crosswalk  # noqa: E402
import build_crosswalk_from_text as bcft  # noqa: E402
import check_no_hardcoded_crosswalk as guardrail  # noqa: E402


# ---------------------------------------------------------------------------
# Guardrail: check_no_hardcoded_crosswalk.py
# ---------------------------------------------------------------------------


class TestGuardrail:
    def test_flags_the_exact_regression_pattern(self):
        # This is the literal shape of the deleted fix_unit1_lessons.py --
        # the pattern this guardrail exists to prevent from reappearing.
        source = """
CCSS_TO_GA = {
    "L.1.1b": ["1.L.GC.1.9"],
    "L.1.1c": ["1.L.GC.2.c"],
    "L.1.1d": ["1.L.GC.1.15"],
}
"""
        findings = guardrail.scan_source(source, "reconstructed.py")
        assert findings, "guardrail must catch a 3+ entry code-to-code dict literal"
        assert "reconstructed.py" in findings[0]

    def test_ignores_a_two_entry_dict(self):
        # Below MIN_ENTRIES_TO_FLAG -- a couple of code-like strings can be a
        # coincidental docstring example, not a mapping table.
        source = """
PAIR = {"L.1.1b": ["1.L.GC.1.9"], "L.1.1c": ["1.L.GC.2.c"]}
"""
        assert guardrail.scan_source(source, "f.py") == []

    def test_ignores_dict_with_non_code_values(self):
        source = """
CONFIG = {
    "L.1.1b": "some description, not a standard code",
    "L.1.1c": "another description",
    "L.1.1d": "a third one",
}
"""
        assert guardrail.scan_source(source, "f.py") == []

    def test_ignores_unrelated_dict(self):
        source = """
COLORS = {"red": ["ff0000"], "green": ["00ff00"], "blue": ["0000ff"]}
"""
        assert guardrail.scan_source(source, "f.py") == []

    def test_handles_syntax_error_gracefully(self):
        assert guardrail.scan_source("def broken(:", "f.py") == []

    @pytest.mark.parametrize(
        "code",
        ["L.1.1b", "L.1.1c", "L.1.4a", "RL.1.7", "SL.1.1a", "W.1.8", "L.1.6", "L.K.1a"],
    )
    def test_recognizes_ccss_shaped_codes(self, code):
        assert guardrail._looks_like_code(code)

    @pytest.mark.parametrize("code", ["1.L.GC.2.c", "1.T.SS.1.b", "1.L.GC.1.9"])
    def test_recognizes_ga_shaped_codes(self, code):
        assert guardrail._looks_like_code(code)

    @pytest.mark.parametrize("value", ["1.2.3.4", "hello world", "", "42"])
    def test_rejects_non_code_strings(self, value):
        assert not guardrail._looks_like_code(value)

    def test_scripts_standalone_itself_is_clean(self):
        # The guardrail must not flag its own toolset -- these tools are
        # CSV-driven by design and contain no mapping dicts.
        findings = guardrail.scan_paths([SCRIPTS_DIR])
        assert findings == []


# ---------------------------------------------------------------------------
# build_crosswalk_from_text.py
# ---------------------------------------------------------------------------


class TestTokenize:
    def test_strips_stopwords_and_lowercases(self):
        assert bcft.tokenize("Use THE common Nouns") == ["use", "common", "nouns"]

    def test_strips_parenthetical_scaffolding_tags(self):
        assert bcft.tokenize("Continue (Introduce) working on adjectives") == [
            "continue",
            "working",
            "adjectives",
        ]

    def test_drops_single_letter_tokens(self):
        assert "a" not in bcft.tokenize("a cat and a dog")


class TestCollocations:
    def test_detects_a_fixed_phrase_across_corpus(self):
        token_lists = [
            ["frequently", "occurring", "adjectives"],
            ["frequently", "occurring", "prepositions"],
            ["frequently", "occurring", "nouns"],
        ]
        collocations = bcft.find_collocations(token_lists, min_ratio=0.7)
        assert ("frequently", "occurring") in collocations

    def test_does_not_flag_a_one_off_pair(self):
        token_lists = [
            ["frequently", "occurring", "adjectives"],
            ["rare", "verbs"],
            ["some", "nouns"],
        ]
        collocations = bcft.find_collocations(token_lists, min_ratio=0.7)
        assert ("frequently", "occurring") not in collocations

    def test_apply_collocations_merges_pair_into_one_token(self):
        merged = bcft.apply_collocations(
            ["use", "frequently", "occurring", "adjectives"],
            {("frequently", "occurring")},
        )
        assert merged == ["use", "frequently_occurring", "adjectives"]

    def test_apply_collocations_no_op_when_no_match(self):
        tokens = ["use", "common", "nouns"]
        assert bcft.apply_collocations(tokens, set()) == tokens


class TestIdfAndCosine:
    def test_common_word_gets_lower_idf_than_rare_word(self):
        token_lists = [["the", "cat"], ["the", "dog"], ["the", "bird"], ["rare", "fox"]]
        idf = bcft.build_idf(token_lists)
        assert idf["the"] < idf["rare"]

    def test_cosine_identical_tokens_is_one(self):
        idf = {"nouns": 1.0, "use": 1.0}
        assert bcft.cosine_sim(["use", "nouns"], ["use", "nouns"], idf) == pytest.approx(1.0)

    def test_cosine_disjoint_tokens_is_zero(self):
        idf = {"nouns": 1.0, "verbs": 1.0}
        assert bcft.cosine_sim(["nouns"], ["verbs"], idf) == 0.0

    def test_cosine_empty_input_is_zero(self):
        assert bcft.cosine_sim([], ["anything"], {}) == 0.0


class TestConfidenceTier:
    @pytest.mark.parametrize(
        "score,expected",
        [(0.9, "high"), (0.45, "high"), (0.44, "medium"), (0.25, "medium"), (0.1, "low"), (0.0, "low")],
    )
    def test_boundaries(self, score, expected):
        assert bcft.confidence_tier(score) == expected


class TestBuildCrosswalkEndToEnd:
    def _write_standard(self, standards_dir: Path, code: str, text: str) -> None:
        (standards_dir / f"{code}.json").write_text(
            json.dumps({"standard_code": code, "raw_text": text}), encoding="utf-8"
        )

    def test_top_candidate_is_the_semantically_closest_standard(self, tmp_path):
        standards_dir = tmp_path / "standards"
        standards_dir.mkdir()
        self._write_standard(standards_dir, "TARGET.MATCH", "Use singular and plural nouns with matching verbs.")
        self._write_standard(standards_dir, "TARGET.UNRELATED", "Draw a picture and write a caption about it.")

        source_csv = tmp_path / "source.csv"
        with source_csv.open("w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["source_code", "source_text"])
            writer.writerow(["SRC.1", "Use singular and plural nouns with matching verbs in basic sentences."])

        out_csv = tmp_path / "out.csv"
        bcft.main(
            [
                "--source-csv",
                str(source_csv),
                "--standards-dir",
                str(standards_dir),
                "--out",
                str(out_csv),
                "--candidates-per-code",
                "2",
            ]
        )

        rows = list(csv.DictReader(out_csv.open(newline="", encoding="utf-8")))
        assert rows[0]["source_code"] == "SRC.1"
        assert rows[0]["target_code"] == "TARGET.MATCH"
        assert rows[0]["confidence"] == "high"


# ---------------------------------------------------------------------------
# apply_crosswalk.py
# ---------------------------------------------------------------------------


class TestLoadCrosswalk:
    def _write_crosswalk(self, path: Path, rows: list[dict[str, str]]) -> None:
        with path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=["source_code", "target_code", "confidence"])
            writer.writeheader()
            writer.writerows(rows)

    def test_filters_below_min_confidence(self, tmp_path):
        path = tmp_path / "crosswalk.csv"
        self._write_crosswalk(
            path,
            [
                {"source_code": "S.1", "target_code": "T.1", "confidence": "high"},
                {"source_code": "S.1", "target_code": "T.2", "confidence": "low"},
            ],
        )
        result = apply_crosswalk.load_crosswalk(path, "high")
        assert result["S.1"] == ["T.1"]

    def test_includes_at_or_above_threshold(self, tmp_path):
        path = tmp_path / "crosswalk.csv"
        self._write_crosswalk(
            path,
            [
                {"source_code": "S.1", "target_code": "T.1", "confidence": "medium"},
                {"source_code": "S.1", "target_code": "T.2", "confidence": "high"},
            ],
        )
        result = apply_crosswalk.load_crosswalk(path, "medium")
        assert result["S.1"] == ["T.1", "T.2"]

    def test_dedupes_repeated_target(self, tmp_path):
        path = tmp_path / "crosswalk.csv"
        self._write_crosswalk(
            path,
            [
                {"source_code": "S.1", "target_code": "T.1", "confidence": "high"},
                {"source_code": "S.1", "target_code": "T.1", "confidence": "high"},
            ],
        )
        result = apply_crosswalk.load_crosswalk(path, "high")
        assert result["S.1"] == ["T.1"]


class TestStandardText:
    def test_reads_raw_text_from_json(self, tmp_path):
        apply_crosswalk._text_cache.clear()
        (tmp_path / "T.STXT.1.json").write_text(json.dumps({"raw_text": "some standard text"}), encoding="utf-8")
        assert apply_crosswalk.standard_text(tmp_path, "T.STXT.1") == "some standard text"

    def test_falls_back_to_competency_statement(self, tmp_path):
        apply_crosswalk._text_cache.clear()
        (tmp_path / "T.STXT.2.json").write_text(
            json.dumps({"raw_text": "", "competency_statement": "fallback text"}), encoding="utf-8"
        )
        assert apply_crosswalk.standard_text(tmp_path, "T.STXT.2") == "fallback text"

    def test_missing_file_returns_placeholder(self, tmp_path):
        apply_crosswalk._text_cache.clear()
        assert apply_crosswalk.standard_text(tmp_path, "NOPE.1") == "(standard text not found)"

    def test_caches_result(self, tmp_path, monkeypatch):
        apply_crosswalk._text_cache.clear()
        (tmp_path / "T.STXT.3.json").write_text(json.dumps({"raw_text": "cached text"}), encoding="utf-8")
        first = apply_crosswalk.standard_text(tmp_path, "T.STXT.3")
        (tmp_path / "T.STXT.3.json").unlink()
        second = apply_crosswalk.standard_text(tmp_path, "T.STXT.3")
        assert first == second == "cached text"


class TestApplyCrosswalkEndToEnd:
    def _setup(self, tmp_path):
        lessons_dir = tmp_path / "lessons"
        top_n_dir = tmp_path / "top_n"
        standards_dir = tmp_path / "standards"
        out_dir = tmp_path / "out"
        for d in (lessons_dir, top_n_dir, standards_dir):
            d.mkdir()
        return lessons_dir, top_n_dir, standards_dir, out_dir

    def test_inserts_missing_crosswalk_match_and_logs_changelog(self, tmp_path):
        lessons_dir, top_n_dir, standards_dir, out_dir = self._setup(tmp_path)

        (lessons_dir / "LESSON1.json").write_text(
            json.dumps({"declared_standards": ["SRC.CODE"]}), encoding="utf-8"
        )
        (standards_dir / "TGT.CODE.json").write_text(
            json.dumps({"raw_text": "target standard text"}), encoding="utf-8"
        )
        with (top_n_dir / "LESSON1_top3.csv").open("w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["rank", "standard_code", "standard_text"])
            writer.writerow([1, "OTHER.CODE", "unrelated text"])

        crosswalk_csv = tmp_path / "crosswalk.csv"
        with crosswalk_csv.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=["source_code", "target_code", "confidence"])
            writer.writeheader()
            writer.writerow({"source_code": "SRC.CODE", "target_code": "TGT.CODE", "confidence": "high"})

        changelog = tmp_path / "changelog.csv"
        apply_crosswalk.main(
            [
                "--lessons-dir", str(lessons_dir),
                "--top-n-dir", str(top_n_dir),
                "--standards-dir", str(standards_dir),
                "--crosswalk", str(crosswalk_csv),
                "--out-dir", str(out_dir),
                "--changelog", str(changelog),
                "--min-confidence", "high",
                "--insert-at-rank", "2",
                "--top-n", "3",
            ]
        )

        out_rows = list(csv.DictReader((out_dir / "LESSON1_top3.csv").open(newline="", encoding="utf-8")))
        codes = [r["standard_code"] for r in out_rows]
        assert "TGT.CODE" in codes

        changelog_rows = list(csv.DictReader(changelog.open(newline="", encoding="utf-8")))
        added = [r for r in changelog_rows if r["action"] == "added" and r["standard_code"] == "TGT.CODE"]
        assert added and added[0]["lesson"] == "LESSON1"

    def test_leaves_file_untouched_when_no_missing_match(self, tmp_path):
        lessons_dir, top_n_dir, standards_dir, out_dir = self._setup(tmp_path)

        (lessons_dir / "LESSON2.json").write_text(
            json.dumps({"declared_standards": ["SRC.CODE"]}), encoding="utf-8"
        )
        original = "rank,standard_code,standard_text\n1,TGT.CODE,already present\n"
        (top_n_dir / "LESSON2_top3.csv").write_text(original, encoding="utf-8")

        crosswalk_csv = tmp_path / "crosswalk.csv"
        with crosswalk_csv.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=["source_code", "target_code", "confidence"])
            writer.writeheader()
            writer.writerow({"source_code": "SRC.CODE", "target_code": "TGT.CODE", "confidence": "high"})

        changelog = tmp_path / "changelog.csv"
        apply_crosswalk.main(
            [
                "--lessons-dir", str(lessons_dir),
                "--top-n-dir", str(top_n_dir),
                "--standards-dir", str(standards_dir),
                "--crosswalk", str(crosswalk_csv),
                "--out-dir", str(out_dir),
                "--changelog", str(changelog),
            ]
        )

        assert (out_dir / "LESSON2_top3.csv").read_text(encoding="utf-8") == original

    def test_copies_through_when_no_matching_lesson_record(self, tmp_path):
        lessons_dir, top_n_dir, standards_dir, out_dir = self._setup(tmp_path)
        original = "rank,standard_code,standard_text\n1,SOME.CODE,text\n"
        (top_n_dir / "NOLESSON_top3.csv").write_text(original, encoding="utf-8")

        crosswalk_csv = tmp_path / "crosswalk.csv"
        crosswalk_csv.write_text("source_code,target_code,confidence\n", encoding="utf-8")
        changelog = tmp_path / "changelog.csv"

        apply_crosswalk.main(
            [
                "--lessons-dir", str(lessons_dir),
                "--top-n-dir", str(top_n_dir),
                "--standards-dir", str(standards_dir),
                "--crosswalk", str(crosswalk_csv),
                "--out-dir", str(out_dir),
                "--changelog", str(changelog),
            ]
        )
        assert (out_dir / "NOLESSON_top3.csv").read_text(encoding="utf-8") == original
