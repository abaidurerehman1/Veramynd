"""Tests for scripts_standalone/build_crosswalk_from_embeddings.py.

Pure-function tests (cosine, confidence_tier, CSV/JSON loaders) run offline.
The accuracy test makes real OpenAI embedding calls against this repo's
19-pair hand-verified ground truth and is skipped when OPENAI_API_KEY is not
set -- it must never be the thing that blocks a key-less CI run, but it is
the actual evidence behind the "73% top-1, 100% precision at high confidence"
claim this tool was built to satisfy.
"""
from __future__ import annotations

import csv
import json
import os
import sys
from collections import defaultdict
from pathlib import Path

import pytest

VERAMYND_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = VERAMYND_ROOT / "_archive" / "scripts_standalone"
sys.path.insert(0, str(SCRIPTS_DIR))

import build_crosswalk_from_embeddings as bce  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[1]
GROUND_TRUTH_CSV = (
    VERAMYND_ROOT
    / "_archive"
    / "reports_scratch"
    / "reference_data"
    / "crosswalk_grade1_unit1_verified.csv"
)
SOURCE_CSV = (
    VERAMYND_ROOT
    / "_archive"
    / "reports_scratch"
    / "reference_data"
    / "ccss_grade1_ela.csv"
)
STANDARDS_DIR = REPO_ROOT / "output" / "normalize_standards"

requires_openai_key = pytest.mark.skipif(
    not os.environ.get("OPENAI_API_KEY"),
    reason="OPENAI_API_KEY not set -- live-API accuracy test skipped",
)


class TestCosine:
    def test_identical_vectors_is_one(self):
        assert bce.cosine([1.0, 2.0, 3.0], [1.0, 2.0, 3.0]) == pytest.approx(1.0)

    def test_orthogonal_vectors_is_zero(self):
        assert bce.cosine([1.0, 0.0], [0.0, 1.0]) == pytest.approx(0.0)

    def test_opposite_vectors_is_negative_one(self):
        assert bce.cosine([1.0, 0.0], [-1.0, 0.0]) == pytest.approx(-1.0)

    def test_zero_vector_is_zero(self):
        assert bce.cosine([0.0, 0.0], [1.0, 2.0]) == 0.0


class TestConfidenceTier:
    @pytest.mark.parametrize(
        "score,expected",
        [
            (0.9, "high"),
            (bce.HIGH_CONFIDENCE_MIN, "high"),
            (bce.HIGH_CONFIDENCE_MIN - 0.001, "medium"),
            (bce.MEDIUM_CONFIDENCE_MIN, "medium"),
            (bce.MEDIUM_CONFIDENCE_MIN - 0.001, "low"),
            (0.0, "low"),
        ],
    )
    def test_boundaries(self, score, expected):
        assert bce.confidence_tier(score) == expected


class TestLoaders:
    def test_load_target_texts_prefers_raw_text(self, tmp_path):
        (tmp_path / "T.1.json").write_text(
            json.dumps({"standard_code": "T.1", "raw_text": "the real text", "competency_statement": "fallback"}),
            encoding="utf-8",
        )
        assert bce.load_target_texts(tmp_path) == {"T.1": "the real text"}

    def test_load_target_texts_falls_back_to_competency_statement(self, tmp_path):
        (tmp_path / "T.2.json").write_text(
            json.dumps({"standard_code": "T.2", "raw_text": "", "competency_statement": "fallback text"}),
            encoding="utf-8",
        )
        assert bce.load_target_texts(tmp_path) == {"T.2": "fallback text"}

    def test_load_target_texts_skips_entries_with_no_text(self, tmp_path):
        (tmp_path / "T.3.json").write_text(
            json.dumps({"standard_code": "T.3", "raw_text": "", "competency_statement": ""}),
            encoding="utf-8",
        )
        assert bce.load_target_texts(tmp_path) == {}

    def test_load_source_rows(self, tmp_path):
        path = tmp_path / "source.csv"
        with path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["source_code", "source_text"])
            writer.writerow(["S.1", " some text "])
        assert bce.load_source_rows(path) == [("S.1", "some text")]


@requires_openai_key
class TestAccuracyOnGroundTruth:
    """Live-API: reuses the exact call path build_crosswalk_from_embeddings.py
    ships (openai_embed_texts from embed/runner.py) against this repo's
    hand-verified Grade-1 Unit-1 crosswalk. Regression guard: if a future
    change (different model, different similarity function) drops accuracy
    well below what was measured when this tool was built, this test catches
    it instead of a silent quality regression shipping unnoticed.
    """

    @pytest.fixture(scope="class")
    def crosswalk_rows(self):
        target_texts = bce.load_target_texts(STANDARDS_DIR)
        source_rows = bce.load_source_rows(SOURCE_CSV)
        return bce.build_crosswalk(source_rows, target_texts, candidates_per_code=5)

    @pytest.fixture(scope="class")
    def ground_truth(self):
        gt = defaultdict(set)
        with GROUND_TRUTH_CSV.open(newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                gt[row["source_code"]].add(row["target_code"])
        return gt

    def test_top1_accuracy_at_least_70_percent(self, crosswalk_rows, ground_truth):
        by_source = defaultdict(list)
        for row in crosswalk_rows:
            by_source[row["source_code"]].append((row["target_code"], float(row["cosine_similarity"])))
        for cands in by_source.values():
            cands.sort(key=lambda t: -t[1])

        hits = sum(
            1
            for src, targets in ground_truth.items()
            if by_source.get(src) and by_source[src][0][0] in targets
        )
        accuracy = hits / len(ground_truth)
        assert accuracy >= 0.70, f"top-1 accuracy {accuracy:.1%} regressed below the 70% floor"

    def test_high_confidence_top1_is_never_wrong(self, crosswalk_rows, ground_truth):
        """High confidence is the tier apply_crosswalk.py auto-inserts from --
        a wrong "high" match corrupts a top-N list with no human review."""
        by_source = defaultdict(list)
        for row in crosswalk_rows:
            by_source[row["source_code"]].append(
                (row["target_code"], float(row["cosine_similarity"]), row["confidence"])
            )
        for cands in by_source.values():
            cands.sort(key=lambda t: -t[1])

        wrong_high_confidence_top1s = [
            (src, cands[0])
            for src, targets in ground_truth.items()
            for cands in [by_source.get(src, [])]
            if cands and cands[0][2] == "high" and cands[0][0] not in targets
        ]
        assert wrong_high_confidence_top1s == []
