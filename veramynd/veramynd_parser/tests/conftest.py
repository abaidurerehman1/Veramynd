"""Shared test fixtures.

The tests run against the real reference documents in data/samples/. If those
files are not present, the tests that need them are skipped rather than failed — so
the suite still runs in a checkout without the (potentially licensed) source PDFs.
"""

from __future__ import annotations

from pathlib import Path

import pytest

# repo root is two levels up from this file: veramynd_parser/tests/conftest.py
REPO_ROOT = Path(__file__).resolve().parents[2]
SAMPLES = REPO_ROOT / "data" / "samples"
GUIDE_PATH = SAMPLES / "ELA Grade 1 Module 2 Teacher Guide.pdf"
STANDARDS_PATH = SAMPLES / "Grade 1 GA ELA Standards.xlsx"


@pytest.fixture(scope="session")
def guide_path() -> Path:
    if not GUIDE_PATH.exists():
        pytest.skip(f"reference teacher guide not found at {GUIDE_PATH}")
    return GUIDE_PATH


@pytest.fixture(scope="session")
def standards_path() -> Path:
    if not STANDARDS_PATH.exists():
        pytest.skip(f"reference standards file not found at {STANDARDS_PATH}")
    return STANDARDS_PATH


def _docling_available() -> bool:
    import importlib.util

    return importlib.util.find_spec("docling") is not None


@pytest.fixture(scope="session")
def guide(guide_path):
    """The main path: Docling-primary parse (uses the on-disk cache if warm)."""
    if not _docling_available():
        pytest.skip("docling not installed (the default engine)")
    from veramynd_parser import Config, parse_teacher_guide

    return parse_teacher_guide(guide_path, Config(engine="docling"))


@pytest.fixture(scope="session")
def guide_pymupdf(guide_path):
    """The fallback path: PyMuPDF-only, font-tier division (no heavy dependency)."""
    from veramynd_parser import Config, parse_teacher_guide

    return parse_teacher_guide(guide_path, Config(engine="pymupdf"))


@pytest.fixture(scope="session")
def standards(standards_path):
    from veramynd_parser import parse_standards

    return parse_standards(standards_path)


_REFERENCE_GAP_MARKERS = ("docling not installed", "reference teacher guide not found",
                          "reference standards file not found")


def pytest_terminal_summary(terminalreporter, exitstatus, config) -> None:
    """Make a partial-coverage run impossible to mistake for a full one.

    Most of this suite's real structural-correctness assertions (lesson counts,
    standards content, cross-engine agreement) only run against the real
    reference documents in data/samples/ (potentially licensed, so not always
    present) and require the `docling` package (a heavy ML dependency, not always
    installed). Both skip gracefully rather than fail when absent — the right
    default for a checkout without those assets — but a bare "N skipped" in the
    summary line reads the same whether those were N irrelevant tests or N tests
    that establish most of this package's real guarantees. This makes the
    difference impossible to miss.
    """
    skipped = terminalreporter.stats.get("skipped", [])
    if not skipped:
        return

    def _reason(report) -> str:
        longrepr = getattr(report, "longrepr", None)
        if isinstance(longrepr, tuple) and len(longrepr) == 3:
            return str(longrepr[2])
        return str(longrepr or "")

    gap_count = sum(
        1 for r in skipped if any(marker in _reason(r) for marker in _REFERENCE_GAP_MARKERS)
    )
    if gap_count == 0:
        return

    terminalreporter.write_sep("=", "COVERAGE GAP — read before trusting this green run", red=True, bold=True)
    terminalreporter.write_line(
        f"{gap_count} of {len(skipped)} skipped test(s) were skipped because docling "
        "and/or the licensed reference documents in data/samples/ are not available "
        "here.",
        red=True,
    )
    terminalreporter.write_line(
        "Those are most of this suite's real structural-correctness assertions. "
        "A green run in this environment means they did not run — not that they passed.",
        red=True,
    )
