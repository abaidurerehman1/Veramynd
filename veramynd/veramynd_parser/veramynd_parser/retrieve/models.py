"""Retrieval candidates for lesson → standards hybrid search."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class StandardDoc:
    """One embeddable / searchable standard (leaf after filter)."""

    standard_code: str
    text: str
    domain_primary: str = ""
    label: str = ""
    level: str = ""
    grade: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class Candidate:
    """A retrieved standard with funnel diagnostics."""

    standard_code: str
    text: str
    rrf_score: float = 0.0
    dense_rank: int | None = None
    bm25_rank: int | None = None
    dense_score: float | None = None
    bm25_score: float | None = None
    rerank_score: float | None = None
    domain_primary: str = ""
    label: str = ""
    level: str = ""
    grade: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


__all__ = ["Candidate", "StandardDoc"]
