"""Alignable (leaf) standards for enterprise K-12 retrieval.

Alignment is scored at the **terminal** standard code — the unit a district
expects on a report (e.g. ``1.T.RA.1.a``), not a parent folder
(``1.T.RA.1`` / domain / big idea).

Parents compete with near-identical wording in hybrid search and crowd
leaves out of the judge funnel. Retriever corpora therefore keep only
terminals.
"""

from __future__ import annotations

from .models import StandardDoc

# Hierarchy folders — never alignment targets.
_NON_ALIGNABLE_LEVELS = frozenset({"domain", "big_idea"})


def filter_alignable_leaves(docs: list[StandardDoc]) -> list[StandardDoc]:
    """Return terminal (leaf) standards only.

    A code is excluded when:
    - its ``level`` is domain/big_idea, or
    - any other loaded doc lists it as ``parent_code`` (it has children).

    Standards with no children remain (terminal nodes). For GA Grade 1 ELA
    that is exactly the substandard set; the parent-graph rule stays
    framework-agnostic for other states.
    """
    parent_codes: set[str] = set()
    for d in docs:
        raw = ""
        if isinstance(d.metadata, dict):
            raw = (d.metadata.get("parent_code") or "").strip()
        if raw:
            parent_codes.add(raw)

    out: list[StandardDoc] = []
    for d in docs:
        level = (d.level or "").strip().lower()
        if level in _NON_ALIGNABLE_LEVELS:
            continue
        code = (d.standard_code or "").strip()
        if not code or code in parent_codes:
            continue
        out.append(d)
    return out


__all__ = ["filter_alignable_leaves"]
