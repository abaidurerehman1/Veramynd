"""Tests for cache_maintenance.py — classifying/pruning orphaned cache entries
left behind by a PROMPT_VERSION or Docling-version bump.

Regression target: cache format changes (prompt version, Docling version) leave
old content-addressed cache entries permanently orphaned with no tooling to find
or reclaim them (previously the only documented remedy was manually deleting the
whole .docling_cache/ directory). This is not a correctness bug -- content
addressing means a stale entry is simply unreachable, never silently served --
but it is a real, previously-unaddressed hygiene gap.
"""

from __future__ import annotations

from pathlib import Path

from veramynd_parser.cache_maintenance import (
    apply_prune,
    scan_docling_cache,
    scan_normalize_cache,
    scan_normalize_standards_cache,
)
from veramynd_parser.normalize.models import minimal_normalized_lesson
from veramynd_parser.normalize.standard_models import minimal_normalized_standard


def _write_normalized(path: Path, *, prompt_version: str) -> None:
    norm = minimal_normalized_lesson(resource_id="G1M2U1L1", prompt_version=prompt_version)
    path.write_text(norm.model_dump_json(), encoding="utf-8")


def test_scan_normalize_cache_classifies_current_vs_stale(tmp_path: Path):
    _write_normalized(tmp_path / "a.json", prompt_version="normalize_ela.v1")
    _write_normalized(tmp_path / "b.json", prompt_version="normalize_lesson.v4")
    (tmp_path / "corrupt.json").write_text("not json", encoding="utf-8")

    result = scan_normalize_cache(tmp_path, current_prompt_version="normalize_ela.v1")

    assert [p.name for p in result.kept] == ["a.json"]
    assert [p.name for p in result.stale] == ["b.json"]
    assert [p.name for p in result.unreadable] == ["corrupt.json"]


def test_scan_normalize_standards_cache_classifies_by_std_prompt(tmp_path: Path):
    current = minimal_normalized_standard(code="1.F.PA.4").model_copy(
        update={"prompt_version": "normalize_std.v1.0"}
    )
    stale = minimal_normalized_standard(code="1.F.PA.5").model_copy(
        update={"prompt_version": "normalize_std.v0.9"}
    )
    (tmp_path / "a.json").write_text(current.model_dump_json(), encoding="utf-8")
    (tmp_path / "b.json").write_text(stale.model_dump_json(), encoding="utf-8")
    # Lesson records in the standards dir must not be treated as current.
    _write_normalized(tmp_path / "lesson.json", prompt_version="normalize_ela.v2.1")

    result = scan_normalize_standards_cache(
        tmp_path, current_prompt_version="normalize_std.v1.0"
    )
    assert [p.name for p in result.kept] == ["a.json"]
    assert [p.name for p in result.stale] == ["b.json"]
    assert [p.name for p in result.unreadable] == ["lesson.json"]


def test_scan_normalize_cache_missing_dir_returns_empty(tmp_path: Path):
    result = scan_normalize_cache(tmp_path / "does-not-exist")
    assert result.kept == result.stale == result.unreadable == []


def test_apply_prune_deletes_only_stale_entries(tmp_path: Path):
    current = tmp_path / "a.json"
    stale = tmp_path / "b.json"
    _write_normalized(current, prompt_version="normalize_ela.v1")
    _write_normalized(stale, prompt_version="normalize_lesson.v4")

    result = scan_normalize_cache(tmp_path, current_prompt_version="normalize_ela.v1")
    deleted = apply_prune(result)

    assert deleted == 1
    assert current.exists()
    assert not stale.exists()


def test_scan_docling_cache_classifies_by_filename_version(tmp_path: Path):
    (tmp_path / "abc123-docling210-ocr0-tables1.docling.json").write_text("{}")
    (tmp_path / "def456-docling200-ocr0-tables1.docling.json").write_text("{}")
    # matches the *.docling.json glob but not the internal version-encoding regex
    (tmp_path / "weird-name.docling.json").write_text("{}")
    (tmp_path / "not-a-cache-file.txt").write_text("junk")  # not even glob-matched

    result = scan_docling_cache(tmp_path, current_docling_version="2.10")

    assert [p.name for p in result.kept] == ["abc123-docling210-ocr0-tables1.docling.json"]
    assert [p.name for p in result.stale] == ["def456-docling200-ocr0-tables1.docling.json"]
    assert [p.name for p in result.unreadable] == ["weird-name.docling.json"]


def test_scan_docling_cache_matches_exact_version_string(tmp_path: Path):
    name = "aa11-docling-2.28.0-vabcdef012345-ocr0-tables1.docling.json"
    (tmp_path / name).write_text("{}")
    result = scan_docling_cache(tmp_path, current_docling_version="2.28.0")
    assert [p.name for p in result.kept] == [name]
    assert result.stale == []


def test_scan_docling_cache_recognizes_legacy_filenames_without_tables_suffix(tmp_path: Path):
    """Regression: real legacy cache entries (predating the `-tablesN` field in the
    cache-key builder) look like `<hash>-docling210-ocr1.docling.json` -- no
    `-tablesN` segment at all. The version-encoding regex used to require that
    suffix unconditionally, so these genuine legacy entries -- found sitting in
    this project's own .docling_cache/ -- were misclassified as 'unreadable'
    instead of 'stale', meaning `cache-prune --apply` could never delete them."""
    (tmp_path / "74c6b2d5ca19cffd-docling21140-ocr1.docling.json").write_text("{}")
    (tmp_path / "75ef8a6887efa2ac-docling21140-ocr0.docling.json").write_text("{}")

    # A newer installed version so these legacy "21140" entries are genuinely stale
    # (not just a version match on the compressed legacy form -- see
    # test_scan_docling_cache_matches_legacy_compressed_form for that case).
    result = scan_docling_cache(tmp_path, current_docling_version="2.115.0")

    assert result.unreadable == []
    assert {p.name for p in result.stale} == {
        "74c6b2d5ca19cffd-docling21140-ocr1.docling.json",
        "75ef8a6887efa2ac-docling21140-ocr0.docling.json",
    }


def test_scan_docling_cache_matches_legacy_compressed_form(tmp_path: Path):
    """A no-`-tablesN` legacy filename still matches its *current* installed
    version via the dot-stripped compressed comparison (`2.114.0` -> `21140`)."""
    (tmp_path / "74c6b2d5ca19cffd-docling21140-ocr1.docling.json").write_text("{}")

    result = scan_docling_cache(tmp_path, current_docling_version="2.114.0")

    assert result.unreadable == []
    assert result.stale == []
    assert [p.name for p in result.kept] == ["74c6b2d5ca19cffd-docling21140-ocr1.docling.json"]


def test_scan_docling_cache_unknown_current_version_keeps_everything(tmp_path: Path):
    """Docling not being installed right now says nothing about whether its
    cache is still valid for whoever installs it next -- must not guess stale."""
    (tmp_path / "abc123-docling210-ocr0-tables1.docling.json").write_text("{}")

    result = scan_docling_cache(tmp_path, current_docling_version=None)

    assert len(result.kept) == 1
    assert result.stale == []
