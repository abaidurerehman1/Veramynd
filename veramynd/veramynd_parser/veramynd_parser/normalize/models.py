"""ELA curriculum-normalization contracts (Stage 3).

Records follow ``ela_normalization_template.blank.json`` / the ELA profile schema.
They are standards-agnostic: no standard codes. Pipeline metadata
(``prompt_version``, ``provider``, ``model``, page range) is stamped by the
caller for cache/provenance join — not produced by the LLM.
"""

from __future__ import annotations

import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

_STRICT = ConfigDict(extra="forbid")

CognitiveDemand = Literal[
    "DOK1_recall_reproduction",
    "DOK2_skills_concepts",
    "DOK3_strategic_thinking",
    "DOK4_extended_thinking",
]
Emphasis = Literal["primary", "secondary", "incidental"]
DomainPrimary = Literal[
    "Phonological Awareness",
    "Phonics",
    "Fluency",
    "Vocabulary",
    "Comprehension",
    "Writing",
    "Language",
    "Speaking & Listening",
]
ResourceType = Literal[
    "unit",
    "main_lesson",
    "lesson_component",
    "routine",
    "supplemental",
    "skill_builder",
    "practice_activity",
    "assessment",
    "intervention",
    "enrichment",
    "ancillary",
    "connection",
]
Actor = Literal["student", "teacher", "shared", "unspecified"]
EvidenceRole = Literal[
    "directive_prompt",
    "student_production",
    "elicitation_check",
    "teacher_model",
    "teacher_scribe",
    "assessment_item",
]
SupportLevel = Literal["independent", "with_prompting", "modeled", "not_applicable"]
IcMode = Literal["interpretation", "construction", "both"]
Genre = Literal["narrative", "expository", "opinion", "poetic", "mixed", "n/a"]
YesNo = Literal["yes", "no"]

STUDENT_ACTION_KEYS: tuple[str, ...] = (
    "recognition_identification",
    "oral_production",
    "written_production",
    "matching_sorting_sequencing",
    "procedural_application",
    "investigation_handson",
    "representation_modeling",
    "reasoning_explanation",
    "comprehension_response",
)

NONE_OBSERVED = "NONE OBSERVED"


class TaughtSkill(BaseModel):
    model_config = _STRICT

    skill: str = Field(description="Concrete sub-skill, framework-neutral — no standard code.")
    cognitive_demand: CognitiveDemand
    # Optional per blank template / README (balance-of-representation).
    emphasis: Emphasis | None = None


class EvidenceItem(BaseModel):
    model_config = _STRICT

    quote: str = Field(description="Verbatim source text — not a paraphrase.")
    location: str = Field(description="Page/section reference for audit.")
    actor: Actor
    evidence_role: EvidenceRole
    support: SupportLevel
    qualifiers: list[str] = Field(default_factory=list)
    supports_action: list[str] = Field(
        default_factory=list,
        description="student_actions keys this quote proves; [] for teacher_model/teacher_scribe.",
    )


class StudentActionsCore(BaseModel):
    """Nine universal student-action slots (LLM-facing; no open dict)."""

    model_config = _STRICT

    recognition_identification: str = NONE_OBSERVED
    oral_production: str = NONE_OBSERVED
    written_production: str = NONE_OBSERVED
    matching_sorting_sequencing: str = NONE_OBSERVED
    procedural_application: str = NONE_OBSERVED
    investigation_handson: str = NONE_OBSERVED
    representation_modeling: str = NONE_OBSERVED
    reasoning_explanation: str = NONE_OBSERVED
    comprehension_response: str = NONE_OBSERVED


class StudentActions(StudentActionsCore):
    # Stored on the final record; always {} for OpenAI-assembled records.
    domain_specific: dict[str, str] = Field(default_factory=dict)


FormatKind = Literal["paper-based", "online digital", "blended", ""]
AssessmentType = Literal["formative", "summative", "none"]


class ProvenanceBlock(BaseModel):
    model_config = _STRICT

    program: str = ""
    source_document: str = ""
    grade: str = ""
    jurisdiction: str = ""
    subject: Literal["ELA/Literacy"] = "ELA/Literacy"
    format: FormatKind = ""


class HierarchyBlock(BaseModel):
    model_config = _STRICT

    module: str = ""
    unit: str = ""
    lesson: str = ""
    day: str = ""
    session: str = ""
    component: str = ""


class PlacementBlock(BaseModel):
    model_config = _STRICT

    resource_type: ResourceType = "main_lesson"
    hierarchy: HierarchyBlock = Field(default_factory=HierarchyBlock)
    sequence: str = ""
    pacing: str = ""
    part_of: str | None = None
    children: list[str] = Field(default_factory=list)


class DomainBlock(BaseModel):
    model_config = _STRICT

    primary: DomainPrimary
    secondary: list[DomainPrimary] = Field(default_factory=list)


class TeacherActions(BaseModel):
    model_config = _STRICT

    direct_instruction: str = ""
    prompts_that_cue_student_response: list[str] = Field(default_factory=list)
    with_prompting_and_support: YesNo = "no"


class ScopeBlock(BaseModel):
    model_config = _STRICT

    breadth: str = ""
    depth: str = ""


class ContextBlock(BaseModel):
    model_config = _STRICT

    mode: str = ""
    stimulus_provided: str = ""
    with_visual_support: YesNo = "no"


class SectionsCovered(BaseModel):
    model_config = _STRICT

    warm_up: str = "n/a"
    direct_instruction: str = "n/a"
    guided_practice: str = "n/a"
    independent_application: str = "n/a"
    check_for_understanding: str = "n/a"
    differentiated_reinforce: str = "n/a"
    differentiated_extend: str = "n/a"


class SupportsBlock(BaseModel):
    model_config = _STRICT

    english_language_learners: str = "NONE"
    universal_design_udl: str = "NONE"
    below_level_reinforce: str = "NONE"
    above_level_extend: str = "NONE"


class AssessmentBlock(BaseModel):
    model_config = _STRICT

    type: AssessmentType = "none"
    method: str = ""
    # Blank template uses JSON null when unset.
    recognition_vs_production: str | None = None


class VocabularyBlock(BaseModel):
    model_config = _STRICT

    new: list[str] = Field(default_factory=list)
    review: list[str] = Field(default_factory=list)


class TextComplexity(BaseModel):
    model_config = _STRICT

    quantitative: str = ""
    qualitative: str = ""
    # Optional per ELA schema / blank template — omit when empty on dump.
    reader_and_task: str | None = None


class SubjectProfile(BaseModel):
    model_config = _STRICT

    mode: IcMode
    # Conditionally required for Writing/Comprehension (enforced on NormalizedLesson).
    genre: Genre = "n/a"
    # Omit entirely when domain.primary is not Comprehension (blank: delete object).
    text_complexity: TextComplexity | None = None


class TaughtSkillLlm(BaseModel):
    """LLM-facing skill row; emphasis always present for OpenAI strict mode."""

    model_config = _STRICT

    skill: str
    cognitive_demand: CognitiveDemand
    emphasis: Emphasis


class AssessmentBlockLlm(BaseModel):
    """LLM-facing assessment; null is not allowed in OpenAI strict mode."""

    model_config = _STRICT

    type: AssessmentType = "none"
    method: str = ""
    recognition_vs_production: str = ""


class ElaLlmDraft(BaseModel):
    """Pedagogical fields the LLM fills (identity/provenance stamped afterward)."""

    model_config = _STRICT

    domain_primary: DomainPrimary
    domain_secondary: list[DomainPrimary] = Field(default_factory=list)
    level: str = ""
    objective: str
    what_is_taught: list[TaughtSkillLlm] = Field(min_length=1)
    what_is_NOT_taught: list[str] = Field(default_factory=list)
    student_actions: StudentActionsCore
    evidence: list[EvidenceItem] = Field(min_length=1)
    teacher_actions_direct_instruction: str = ""
    teacher_prompts_that_cue_student_response: list[str] = Field(default_factory=list)
    with_prompting_and_support: YesNo
    scope: ScopeBlock = Field(default_factory=ScopeBlock)
    context: ContextBlock = Field(default_factory=ContextBlock)
    sections_covered: SectionsCovered = Field(default_factory=SectionsCovered)
    supports: SupportsBlock = Field(default_factory=SupportsBlock)
    assessment: AssessmentBlockLlm = Field(default_factory=AssessmentBlockLlm)
    protocols_routines: list[str] = Field(default_factory=list)
    notes: str = ""
    subject_profile_mode: IcMode
    subject_profile_genre: Genre = "n/a"
    text_complexity_quantitative: str = "n/a"
    text_complexity_qualitative: str = "n/a"
    text_complexity_reader_and_task: str = ""
    placement_resource_type: ResourceType = "main_lesson"
    placement_pacing: str = ""


class NormalizedLesson(BaseModel):
    """One ELA curriculum-normalization record for a Stage-1 lesson."""

    model_config = _STRICT

    schema_version: str = "2.0-ela"
    resource_id: str
    title: str

    provenance: ProvenanceBlock = Field(default_factory=ProvenanceBlock)
    placement: PlacementBlock = Field(default_factory=PlacementBlock)
    domain: DomainBlock
    level: str = ""
    objective: str
    what_is_taught: list[TaughtSkill] = Field(min_length=1)
    what_is_NOT_taught: list[str] = Field(default_factory=list)
    student_actions: StudentActions = Field(default_factory=StudentActions)
    evidence: list[EvidenceItem] = Field(min_length=1)
    teacher_actions: TeacherActions = Field(default_factory=TeacherActions)
    example_items: dict[str, str] = Field(default_factory=dict)
    scope: ScopeBlock = Field(default_factory=ScopeBlock)
    context: ContextBlock = Field(default_factory=ContextBlock)
    sections_covered: SectionsCovered = Field(default_factory=SectionsCovered)
    supports: SupportsBlock = Field(default_factory=SupportsBlock)
    assessment: AssessmentBlock = Field(default_factory=AssessmentBlock)
    materials: list[str] = Field(default_factory=list)
    vocabulary: VocabularyBlock = Field(default_factory=VocabularyBlock)
    protocols_routines: list[str] = Field(default_factory=list)
    notes: str = ""
    subject_profile: SubjectProfile

    # Pipeline metadata (not in the public ELA blank template).
    prompt_version: str = ""
    provider: str = ""
    model: str = ""
    source_page_start: int | None = None
    source_page_end: int | None = None

    @property
    def code(self) -> str:
        """Lesson identity alias used by CLI / callers."""
        return self.resource_id

    @model_validator(mode="after")
    def _ela_conditionals_and_coverage(self) -> NormalizedLesson:
        primary = self.domain.primary
        secondary = list(self.domain.secondary or [])
        # Normalize secondary: never repeat primary; no duplicates.
        cleaned_secondary: list[str] = []
        seen: set[str] = set()
        for strand in secondary:
            if not strand or strand == primary or strand in seen:
                continue
            seen.add(strand)
            cleaned_secondary.append(strand)
        if cleaned_secondary != secondary:
            self.domain = self.domain.model_copy(update={"secondary": cleaned_secondary})
            secondary = cleaned_secondary

        strands = {primary, *secondary}
        needs_genre = bool(strands & {"Writing", "Comprehension"})
        needs_tc = "Comprehension" in strands

        if needs_genre and self.subject_profile.genre == "n/a":
            raise ValueError(
                "subject_profile.genre is required when Writing or Comprehension "
                "appears in domain.primary or domain.secondary"
            )
        if needs_tc:
            tc = self.subject_profile.text_complexity
            if tc is None:
                raise ValueError(
                    "subject_profile.text_complexity required when Comprehension "
                    "appears in domain.primary or domain.secondary"
                )
            quant = (tc.quantitative or "").strip()
            qual = (tc.qualitative or "").strip()
            # "n/a" is the LLM placeholder for non-Comprehension — never valid here.
            if not quant or quant.lower() == "n/a" or not qual or qual.lower() == "n/a":
                raise ValueError(
                    "subject_profile.text_complexity.{quantitative,qualitative} must be "
                    "real values when Comprehension is primary or secondary "
                    "(not empty / not 'n/a')"
                )
        elif self.subject_profile.text_complexity is not None:
            # Drop noise when Comprehension is neither primary nor secondary.
            self.subject_profile = self.subject_profile.model_copy(
                update={"text_complexity": None}
            )

        if not self.evidence:
            raise ValueError("evidence must contain ≥1 item")
        for i, item in enumerate(self.evidence):
            if not (item.quote or "").strip():
                raise ValueError(f"evidence[{i}].quote must be non-empty verbatim text")
            for key in item.supports_action:
                if key not in STUDENT_ACTION_KEYS:
                    raise ValueError(
                        f"evidence[{i}].supports_action contains unknown key {key!r}; "
                        f"allowed: {list(STUDENT_ACTION_KEYS)}"
                    )

        claimed = {
            k
            for k in STUDENT_ACTION_KEYS
            if getattr(self.student_actions, k, NONE_OBSERVED).strip()
            and getattr(self.student_actions, k) != NONE_OBSERVED
        }
        covered: set[str] = set()
        for item in self.evidence:
            for key in item.supports_action:
                covered.add(key)
        missing = sorted(claimed - covered)
        if missing:
            raise ValueError(
                "every non-NONE OBSERVED student_actions key must be named by ≥1 "
                f"evidence.supports_action; missing coverage for: {missing}"
            )
        return self


def minimal_normalized_lesson(
    *,
    resource_id: str = "G1M2U1L1",
    prompt_version: str = "",
    title: str = "Sample",
    objective: str = "Students practice a literacy skill.",
) -> NormalizedLesson:
    """Valid minimal record for tests / cache fixtures."""
    return NormalizedLesson(
        resource_id=resource_id,
        title=title,
        provenance=ProvenanceBlock(
            program="test",
            source_document="test.pdf",
            grade="1",
            subject="ELA/Literacy",
        ),
        placement=PlacementBlock(resource_type="main_lesson"),
        domain=DomainBlock(primary="Speaking & Listening"),
        objective=objective,
        what_is_taught=[
            TaughtSkill(
                skill="share an observation with a partner",
                cognitive_demand="DOK1_recall_reproduction",
                emphasis="primary",
            )
        ],
        student_actions=StudentActions(
            oral_production="Turn and talk about an observation.",
        ),
        evidence=[
            EvidenceItem(
                quote="Turn and tell your partner what you notice.",
                location="Opening A",
                actor="student",
                evidence_role="directive_prompt",
                support="with_prompting",
                supports_action=["oral_production"],
            )
        ],
        teacher_actions=TeacherActions(with_prompting_and_support="yes"),
        subject_profile=SubjectProfile(mode="interpretation", genre="n/a"),
        prompt_version=prompt_version,
    )


# Keys that belong to our pipeline only — not in ela_normalization_template.blank.json.
_PIPELINE_KEYS = (
    "prompt_version",
    "provider",
    "model",
    "source_page_start",
    "source_page_end",
)

# Top-level keys of the blank template (scorable record).
_ELA_TEMPLATE_KEYS = (
    "schema_version",
    "resource_id",
    "title",
    "provenance",
    "placement",
    "domain",
    "level",
    "objective",
    "what_is_taught",
    "what_is_NOT_taught",
    "student_actions",
    "evidence",
    "teacher_actions",
    "example_items",
    "scope",
    "context",
    "sections_covered",
    "supports",
    "assessment",
    "materials",
    "vocabulary",
    "protocols_routines",
    "notes",
    "subject_profile",
)


def dump_ela_record(norm: NormalizedLesson) -> dict:
    """Serialize to blank-template shape + ``_pipeline`` (internal join metadata).

    - Omits ``subject_profile.text_complexity`` when not Comprehension
    - Omits empty optional ``emphasis`` / ``reader_and_task``
    - Uses JSON ``null`` for unset ``assessment.recognition_vs_production``
    - Keeps ``example_items`` as ``{}``
    """
    raw = norm.model_dump(mode="json")

    pipeline = {k: raw.pop(k, None) for k in _PIPELINE_KEYS}

    # Rebuild subject_profile: drop text_complexity when None; drop empty reader_and_task.
    sp = raw.get("subject_profile") or {}
    tc = sp.get("text_complexity")
    if tc is None:
        sp.pop("text_complexity", None)
    else:
        if not tc.get("reader_and_task"):
            tc.pop("reader_and_task", None)
        sp["text_complexity"] = tc
    raw["subject_profile"] = sp

    for item in raw.get("what_is_taught") or []:
        if item.get("emphasis") is None:
            item.pop("emphasis", None)

    # Blank template: recognition_vs_production is null when unset.
    assessment = raw.get("assessment") or {}
    if not assessment.get("recognition_vs_production"):
        assessment["recognition_vs_production"] = None
    raw["assessment"] = assessment

    raw["example_items"] = raw.get("example_items") or {}

    ordered = {k: raw[k] for k in _ELA_TEMPLATE_KEYS if k in raw}
    ordered["_pipeline"] = pipeline
    return ordered


def dump_ela_record_json(norm: NormalizedLesson, *, indent: int = 2) -> str:
    return json.dumps(dump_ela_record(norm), indent=indent) + "\n"


def parse_ela_record(data: dict | str) -> NormalizedLesson:
    """Load a dumped ELA record (with or without ``_pipeline``)."""
    if isinstance(data, str):
        payload = json.loads(data)
    else:
        payload = dict(data)

    pipeline = payload.pop("_pipeline", None) or {}
    for k in _PIPELINE_KEYS:
        if k in pipeline and k not in payload:
            payload[k] = pipeline[k]

    # Tolerate legacy flat dumps that already had pipeline keys at top level.
    return NormalizedLesson.model_validate(payload)
