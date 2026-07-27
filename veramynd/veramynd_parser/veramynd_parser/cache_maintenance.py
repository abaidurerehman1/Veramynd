"""Prune orphaned entries from the content-addressed caches."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from pydantic import ValidationError

from .normalize.lesson import PROMPT_VERSION
from .normalize.models import NormalizedLesson

# Matches both legacy (`docling210`) and current (`docling-2.10.0-vabcdef`) keys.
# The `-tablesN` suffix is mandatory for the current form (the running cache-key
# builder in pdf/docling_parser.py always appends it) but optional for the legacy
# form: real cache entries from before that field existed look like
# `<hash>-docling210-ocr1.docling.json` (no `-tablesN` at all), not
# `<hash>-docling210-ocr1-tables1.docling.json` as an earlier version of this
# regex assumed -- which made scan_docling_cache() misclassify genuine legacy
# entries as "unreadable" instead of "stale", so `cache-prune --apply` silently
# never deleted them.
_DOCLING_CACHE_NAME = re.compile(
    r"^[0-9a-f]+-docling(?:"
    r"-(?P<version_full>[^-]+)-v[0-9a-f]+-ocr[01]-tables[01]"
    r"|(?P<version_legacy>[0-9]+)-ocr[01](?:-tables[01])?"
    r")\.docling\.json$"
)


@dataclass(frozen=True)
class PruneResult:
    """Classification of one cache directory's entries."""

    kept: list[Path] = field(default_factory=list)
    stale: list[Path] = field(default_factory=list)
    unreadable: list[Path] = field(default_factory=list)

    @property
    def stale_bytes(self) -> int:
        return sum(p.stat().st_size for p in self.stale if p.exists())


def scan_normalize_cache(
    cache_dir: Path | str, *, current_prompt_version: str = PROMPT_VERSION
) -> PruneResult:
    """Classify ``.normalize_cache/*.json`` entries as current or stale."""
    cache_dir = Path(cache_dir)
    result = PruneResult()
    if not cache_dir.is_dir():
        return result
    for path in sorted(cache_dir.glob("*.json")):
        try:
            norm = NormalizedLesson.model_validate_json(path.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError, ValidationError):
            result.unreadable.append(path)
            continue
        (result.kept if norm.prompt_version == current_prompt_version else result.stale).append(path)
    return result


def scan_docling_cache(
    cache_dir: Path | str, *, current_docling_version: str | None
) -> PruneResult:
    """Classify Docling cache files by the version encoded in their filename."""
    cache_dir = Path(cache_dir)
    result = PruneResult()
    if not cache_dir.is_dir():
        return result
    for path in sorted(cache_dir.glob("*.docling.json")):
        m = _DOCLING_CACHE_NAME.match(path.name)
        if not m:
            result.unreadable.append(path)
            continue
        file_version = m.group("version_full") or m.group("version_legacy")
        if current_docling_version is None:
            result.kept.append(path)
            continue
        # Compare exact version string, or legacy compressed form.
        legacy_current = current_docling_version.replace(".", "")
        if file_version in (current_docling_version, legacy_current):
            result.kept.append(path)
        else:
            result.stale.append(path)
    return result


def apply_prune(result: PruneResult) -> int:
    """Delete every ``stale`` path (never ``kept`` or ``unreadable``)."""
    n = 0
    for path in result.stale:
        path.unlink(missing_ok=True)
        n += 1
    return n


def installed_docling_version() -> str | None:
    """The installed ``docling`` package version, or None if not importable."""
    import importlib.metadata

    try:
        return importlib.metadata.version("docling")
    except importlib.metadata.PackageNotFoundError:
        return None
