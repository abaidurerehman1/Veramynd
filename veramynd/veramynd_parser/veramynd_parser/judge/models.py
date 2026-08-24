"""Alignment judge contracts (lesson × standard verdicts)."""

from __future__ import annotations

import json
import re
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

MatchedStatus = Literal["full", "partial", "none"]
Confidence = Literal["high", "medium", "low"]
ClauseClientJudgment = Literal["met", "partially_met", "not_met"]
ClauseActor = Literal["student", "teacher", "none"]

_PAGE_IN_LOCATION = re.compile(r"(?i)\bpage\s+(\d+)\b")


def page_from_location(location: str | None) -> int | None:
    """Parse ``page N`` from a client location string, if present."""
    m = _PAGE_IN_LOCATION.search(location or "")
    if not m:
        return None
    return int(m.group(1))


class ClauseJudgment(BaseModel):
    """Per-clause decision inside one standard (pipeline contract)."""

    clause: str = Field(description="One independent requirement from the standard.")
    met: bool = Field(description="True if students perform this clause in the lesson.")
    note: str = Field(description="Brief reason; empty string if none.")


class ClauseClientDraft(BaseModel):
    """One clause object from the client engine JSON."""

    clause: str = Field(description="Clause text derived in Step 1.")
    judgment: ClauseClientJudgment = Field(
        description="met | partially_met | not_met for this clause."
    )
    actor: ClauseActor = Field(
        description="Who performed the quoted act: student | teacher | none."
    )
    student_quote: str = Field(
        description=(
            "Verbatim resource text of the student act or student-directed "
            "imperative; empty when not_met. No [bracketed] glosses or paraphrase."
        )
    )
    teacher_quote: str = Field(
        default="",
        description="Optional teacher-voiced line; never justifies met.",
    )
    why: str = Field(
        default="",
        description="Short phrase tying student_quote to the clause; empty on none.",
    )

    def to_clause(self) -> ClauseJudgment:
        if self.judgment == "met":
            note = (self.why or "").strip()
        elif self.judgment == "partially_met":
            note = (self.why or "").strip() or "partially met"
        else:
            note = (self.why or "").strip() or "not met"
        return ClauseJudgment(
            clause=self.clause,
            met=self.judgment == "met",
            note=note,
        )


class JudgeLlmDraft(BaseModel):
    """Internal judge draft after mapping client JSON (or test mocks)."""

    matched_status: MatchedStatus = Field(
        description="full = all clauses met; partial = some; none = none / gated out."
    )
    clauses: list[ClauseJudgment] = Field(
        min_length=1,
        description="Decomposed clauses with per-clause met flags (at least one).",
    )
    evidence: str = Field(
        description=(
            "Verbatim quote from the lesson showing students performing the act; "
            "empty string if matched_status is none."
        )
    )
    evidence_page: int | None = Field(
        description="Page number from lesson blocks if known; null if unknown."
    )
    confidence: Confidence = Field(
        description="Mapped from needs_review (low) or high when unflagged."
    )
    rationale: str = Field(
        description="Short explanation of the verdict (1-3 sentences)."
    )
    needs_review: bool = False
    review_reason: str = ""
    evidence_candidates: list[str] = Field(
        default_factory=list,
        description="All student_quote values; used to pick a grounded quote.",
    )


class JudgeClientDraft(BaseModel):
    """Client engine JSON for one candidate (pair call / structured-output object)."""

    candidate_id: str = Field(default="", description="Lesson / resource id.")
    location: str = Field(default="", description="Unit/day/page/section if known.")
    standard_code: str = Field(default="", description="Standard code being scored.")
    clauses: list[ClauseClientDraft] = Field(
        min_length=1,
        description="Clause judgments from Steps 1–2.",
    )
    alignment: MatchedStatus = Field(description="full | partial | none from Step 3.")
    needs_review: bool = Field(
        description="True only when an overlay review-flag trigger fires."
    )
    review_reason: str = Field(
        default="",
        description="Ambiguity + two candidate labels; empty when not flagged.",
    )
    evidence: str = Field(
        description="2–4 sentence justification with student quote; empty on none."
    )
    anchor_note: str = Field(
        default="",
        description="Optional note if the resource reaches toward the anchor.",
    )

    def to_llm_draft(self) -> JudgeLlmDraft:
        clauses = [c.to_clause() for c in self.clauses]
        writeup = (self.evidence or "").strip()
        quotes: list[str] = []
        if self.alignment != "none":
            for c in self.clauses:
                q = (c.student_quote or "").strip()
                if q:
                    quotes.append(q)
        evidence = quotes[0] if quotes else ""
        rationale = writeup or (self.review_reason or "").strip()
        if not rationale:
            rationale = f"alignment={self.alignment}"
        return JudgeLlmDraft(
            matched_status=self.alignment,
            clauses=clauses,
            evidence=evidence,
            evidence_page=page_from_location(self.location),
            confidence="low" if self.needs_review else "high",
            rationale=rationale,
            needs_review=self.needs_review,
            review_reason=(self.review_reason or "").strip(),
            evidence_candidates=quotes,
        )


class JudgeBatchItem(BaseModel):
    """One standard's draft inside a batched judge response (internal)."""

    standard_code: str = Field(description="Exact standard_code from the input list.")
    matched_status: MatchedStatus = Field(
        description="full = all clauses met; partial = some; none = none / gated out."
    )
    clauses: list[ClauseJudgment] = Field(
        min_length=1,
        description="Decomposed clauses with per-clause met flags (at least one).",
    )
    evidence: str = Field(
        description=(
            "Verbatim quote from the lesson showing students performing the act; "
            "empty string if matched_status is none."
        )
    )
    evidence_page: int | None = Field(
        description="Page number from lesson blocks if known; null if unknown."
    )
    confidence: Confidence = Field(
        description="Mapped from needs_review (low) or high when unflagged."
    )
    rationale: str = Field(
        description="Short explanation of the verdict (1-3 sentences)."
    )
    needs_review: bool = False
    review_reason: str = ""
    evidence_candidates: list[str] = Field(default_factory=list)

    def to_draft(self) -> JudgeLlmDraft:
        return JudgeLlmDraft(
            matched_status=self.matched_status,
            clauses=self.clauses,
            evidence=self.evidence,
            evidence_page=self.evidence_page,
            confidence=self.confidence,
            rationale=self.rationale,
            needs_review=self.needs_review,
            review_reason=self.review_reason,
            evidence_candidates=list(self.evidence_candidates),
        )


class JudgeClientBatchItem(JudgeClientDraft):
    """Client engine JSON for one candidate inside a batch ``results`` array."""

    standard_code: str = Field(description="Exact standard_code from the input list.")

    def to_batch_item(self) -> JudgeBatchItem:
        draft = self.to_llm_draft()
        return JudgeBatchItem(
            standard_code=(self.standard_code or "").strip(),
            matched_status=draft.matched_status,
            clauses=draft.clauses,
            evidence=draft.evidence,
            evidence_page=draft.evidence_page,
            confidence=draft.confidence,
            rationale=draft.rationale,
            needs_review=draft.needs_review,
            review_reason=draft.review_reason,
            evidence_candidates=list(draft.evidence_candidates),
        )


class JudgeBatchDraft(BaseModel):
    """Internal batch envelope after mapping client JSON (or test mocks)."""

    results: list[JudgeBatchItem] = Field(
        description="One independent verdict per input standard_code."
    )


class JudgeClientBatchDraft(BaseModel):
    """Structured-output wrapper around the client engine's candidate array."""

    results: list[JudgeClientBatchItem] = Field(
        description="One client candidate object per input standard_code."
    )

    @field_validator("results", mode="before")
    @classmethod
    def _coerce_results_list(cls, value: Any) -> Any:
        """Anthropic sometimes returns the results array as a JSON string."""
        if not isinstance(value, str):
            return value
        text = value.strip()
        if not text:
            return value
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            return value
        return parsed

    def to_batch_draft(self) -> JudgeBatchDraft:
        return JudgeBatchDraft(results=[item.to_batch_item() for item in self.results])


class AlignmentVerdict(BaseModel):
    """Final judged pair with grounding + provenance."""

    schema_version: str = "1.0-judge"
    resource_id: str
    standard_code: str
    matched_status: MatchedStatus
    clauses: list[ClauseJudgment]
    evidence: str
    evidence_page: int | None = None
    confidence: Confidence
    rationale: str
    grounded: bool
    grounding_note: str = ""
    prompt_version: str
    judge_model: str
    escalated: bool = False
    retrieval: dict[str, Any] = Field(default_factory=dict)
    standard_raw_text: str = ""
    needs_review: bool = False
    review_reason: str = ""
    input_scope_caveat: str = ""

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


class CachedBatchVerdicts(BaseModel):
    """Disk-cache envelope for a full lesson batch of verdicts."""

    verdicts: list[AlignmentVerdict]


__all__ = [
    "AlignmentVerdict",
    "CachedBatchVerdicts",
    "ClauseClientDraft",
    "ClauseJudgment",
    "Confidence",
    "JudgeBatchDraft",
    "JudgeBatchItem",
    "JudgeClientBatchDraft",
    "JudgeClientBatchItem",
    "JudgeClientDraft",
    "JudgeLlmDraft",
    "MatchedStatus",
    "page_from_location",
]
