"""Shared path / file helpers used by multiple stages."""

from __future__ import annotations

from pathlib import Path

# Sidecar / progress / manifest JSON that must never be treated as a lesson.
NON_LESSON_JSON_NAMES = frozenset(
    {
        "normalize_progress.json",
        "lessons_index.json",
        "teacher_guide.json",
        "standards.json",
        "verification_report.json",
    }
)


def resolve_package_relative(raw: str) -> Path:
    """Resolve a relative path against the ``veramynd_parser`` package root.

    Absolute paths are returned unchanged. Shared by Docling cache, normalize
    cache, and maintenance tools so parents[N] depths cannot drift.
    """
    path = Path(raw)
    if path.is_absolute():
        return path
    # veramynd_parser/veramynd_parser/paths.py → parents[1] == package root
    return Path(__file__).resolve().parents[1] / path


def iter_lesson_json_files(directory: Path | str) -> list[Path]:
    """Lesson JSON files in ``directory``, excluding known non-lesson sidecars.

    Used by ``normalize_lessons_dir`` so discovery rules stay consistent.
    """
    src = Path(directory)
    if not src.is_dir():
        raise FileNotFoundError(f"directory not found: {src}")
    return sorted(
        p
        for p in src.glob("*.json")
        if p.name not in NON_LESSON_JSON_NAMES and not p.name.endswith(".bak")
    )
