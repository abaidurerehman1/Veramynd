"""Normalized-standard contracts aligned with lesson ELA normalize vocabulary.

Retrieval compares concept↔concept (architecture §7). Fields mirror lesson-side
``domain`` / ``student_actions`` / skill language so hybrid search can match.
Raw standard text is preserved for the later judge (never replaced).
"""

from __future__ import annotations

import json

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ..models import StandardLevel
from .models import (
    NONE_OBSERVED,
    STUDENT_ACTION_KEYS,
    CognitiveDemand,
    DomainBlock,
    DomainPrimary,
    StudentActions,
    StudentActionsCore,
)

_STRICT = ConfigDict(extra="forbid")

STD_SCHEMA_VERSION = "1.0-std"


class StandardLlmDraft(BaseModel):
    """Pedagogical fields the LLM fills for one standard / substandard."""

    model_config = _STRICT

    domain_primary: DomainPrimary
    domain_secondary: list[DomainPrimary] = Field(default_factory=list)
    competency_statement: str = Field(
        description="What the student must be able to do, in plain classroom language."
    )
    observable_behaviors: list[str] = Field(
        min_length=1,
        description="What it looks like in a classroom when this standard is taught.",
    )
    pedagogy_terms: list[str] = Field(
        default_factory=list,
        description="Shared retrieval terms (science-of-reading / classroom vocabulary).",
    )
    student_actions: StudentActionsCore
    cognitive_demand: CognitiveDemand
    skill_clauses: list[str] = Field(
        min_length=1,
        description="Clause-level skills (framework-neutral), one clause per item.",
    )
    notes: str = ""


class NormalizedStandard(BaseModel):
    """One retrieval-ready normalized standard record."""

    model_config = _STRICT

    schema_version: str = STD_SCHEMA_VERSION
    standard_code: str
    level: StandardLevel
    grade: int
    framework: str = ""
    label: str = ""
    raw_text: str = Field(description="Verbatim Stage-1 standard text (judge lane).")
    parent_code: str | None = None
    ancestor_path: list[str] = Field(
        default_factory=list,
        description="Codes from domain down to parent (exclusive of self).",
    )
    child_codes: list[str] = Field(default_factory=list)
    child_texts: list[str] = Field(
        default_factory=list,
        description="Child node texts included as LLM context (not invented).",
    )

    domain: DomainBlock
    competency_statement: str
    observable_behaviors: list[str] = Field(min_length=1)
    pedagogy_terms: list[str] = Field(default_factory=list)
    exact_codes: list[str] = Field(
        min_length=1,
        description="This code (+ any aliases) for BM25 exact lookup.",
    )
    skill_clauses: list[str] = Field(min_length=1)
    student_actions: StudentActions
    cognitive_demand: CognitiveDemand
    notes: str = ""

    # Deterministic retrieval text stamped after assemble (not LLM-authored).
    embed_text: str = ""

    prompt_version: str = ""
    provider: str = ""
    model: str = ""

    @model_validator(mode="after")
    def _validate_record(self) -> NormalizedStandard:
        if self.standard_code not in self.exact_codes:
            raise ValueError(
                f"exact_codes must include standard_code {self.standard_code!r}"
            )
        if not (self.competency_statement or "").strip():
            raise ValueError("competency_statement must be non-empty")
        if not self.observable_behaviors:
            raise ValueError("observable_behaviors must contain ≥1 item")
        if not self.skill_clauses:
            raise ValueError("skill_clauses must contain ≥1 item")
        primary = self.domain.primary
        cleaned: list[str] = []
        seen: set[str] = set()
        for s in self.domain.secondary or []:
            if not s or s == primary or s in seen:
                continue
            seen.add(s)
            cleaned.append(s)
        if list(self.domain.secondary or []) != cleaned:
            self.domain = self.domain.model_copy(update={"secondary": cleaned})
        return self


def build_standard_embed_text(norm: NormalizedStandard) -> str:
    """Compact retrieval text — parallel to lesson competency chunk text."""
    lines: list[str] = [
        f"Standard: {norm.standard_code}",
        f"Domain primary: {norm.domain.primary}",
    ]
    secondary = ", ".join(norm.domain.secondary) if norm.domain.secondary else "none"
    lines.append(f"Domain secondary: {secondary}")
    lines.append(f"Cognitive demand: {norm.cognitive_demand}")
    if norm.competency_statement.strip():
        lines.append(f"Competency: {norm.competency_statement.strip()}")
    if norm.skill_clauses:
        lines.append("Skills:")
        for s in norm.skill_clauses:
            if (s or "").strip():
                lines.append(f"- {s.strip()}")
    if norm.observable_behaviors:
        lines.append("Observable behaviors:")
        for b in norm.observable_behaviors:
            if (b or "").strip():
                lines.append(f"- {b.strip()}")
    terms = [t.strip() for t in norm.pedagogy_terms if (t or "").strip()]
    if terms:
        lines.append("Pedagogy terms: " + ", ".join(terms))
    action_lines: list[str] = []
    for key in STUDENT_ACTION_KEYS:
        val = (getattr(norm.student_actions, key, "") or "").strip()
        if val and val != NONE_OBSERVED:
            action_lines.append(f"- {key}: {val}")
    if action_lines:
        lines.append("Required student actions:")
        lines.extend(action_lines)
    if norm.exact_codes:
        lines.append("Codes: " + ", ".join(norm.exact_codes))
    return "\n".join(lines).strip()


def dump_normalized_standard_json(norm: NormalizedStandard, *, indent: int = 2) -> str:
    return json.dumps(norm.model_dump(mode="json"), indent=indent) + "\n"


def parse_normalized_standard(data: dict | str) -> NormalizedStandard:
    if isinstance(data, str):
        payload = json.loads(data)
    else:
        payload = dict(data)
    return NormalizedStandard.model_validate(payload)


def minimal_normalized_standard(
    *,
    code: str = "1.F.PA.4",
    text: str = "Identify and manipulate syllables in spoken words.",
) -> NormalizedStandard:
    """Fixture helper for tests."""
    return NormalizedStandard(
        standard_code=code,
        level=StandardLevel.STANDARD,
        grade=1,
        framework="GA ELA",
        label="Syllables",
        raw_text=text,
        domain=DomainBlock(primary="Phonological Awareness"),
        competency_statement="Students identify and change syllables in spoken words.",
        observable_behaviors=[
            "Clap or count syllables in spoken words",
            "Add, delete, or substitute a syllable when asked",
        ],
        pedagogy_terms=["syllables", "spoken words", "phonological awareness"],
        exact_codes=[code],
        skill_clauses=[
            "identify syllables in spoken words",
            "manipulate syllables in spoken words",
        ],
        student_actions=StudentActions(
            recognition_identification="identify syllables in spoken words",
            oral_production="produce spoken words after syllable changes",
            procedural_application="add, delete, or substitute syllables on request",
        ),
        cognitive_demand="DOK2_skills_concepts",
        embed_text="",
    )


__all__ = [
    "STD_SCHEMA_VERSION",
    "StandardLlmDraft",
    "NormalizedStandard",
    "build_standard_embed_text",
    "dump_normalized_standard_json",
    "parse_normalized_standard",
    "minimal_normalized_standard",
]
