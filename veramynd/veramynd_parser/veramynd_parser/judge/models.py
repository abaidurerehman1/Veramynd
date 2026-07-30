"""Alignment judge contracts (lesson × standard verdicts)."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

MatchedStatus = Literal["full", "partial", "none"]
Confidence = Literal["high", "medium", "low"]


class ClauseJudgment(BaseModel):
    """Per-clause decision inside one standard."""

    clause: str = Field(description="One independent requirement from the standard.")
    met: bool = Field(description="True if students perform this clause in the lesson.")
    note: str = Field(description="Brief reason; empty string if none.")


class JudgeLlmDraft(BaseModel):
    """Strict JSON schema returned by the judge LLM (one standard per call)."""

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
        description="Self-reported confidence for the report (not a hard filter)."
    )
    rationale: str = Field(
        description="Short explanation of the verdict (1-3 sentences)."
    )


class JudgeBatchItem(BaseModel):
    """One standard's draft inside a batched judge response."""

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
        description="Self-reported confidence for the report (not a hard filter)."
    )
    rationale: str = Field(
        description="Short explanation of the verdict (1-3 sentences)."
    )

    def to_draft(self) -> JudgeLlmDraft:
        return JudgeLlmDraft(
            matched_status=self.matched_status,
            clauses=self.clauses,
            evidence=self.evidence,
            evidence_page=self.evidence_page,
            confidence=self.confidence,
            rationale=self.rationale,
        )


class JudgeBatchDraft(BaseModel):
    """Strict JSON schema for one lesson × N standards in a single LLM call."""

    results: list[JudgeBatchItem] = Field(
        description="One independent verdict per input standard_code."
    )


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

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


class CachedBatchVerdicts(BaseModel):
    """Disk-cache envelope for a full lesson batch of verdicts."""

    verdicts: list[AlignmentVerdict]


__all__ = [
    "AlignmentVerdict",
    "CachedBatchVerdicts",
    "ClauseJudgment",
    "Confidence",
    "JudgeBatchDraft",
    "JudgeBatchItem",
    "JudgeLlmDraft",
    "MatchedStatus",
]
