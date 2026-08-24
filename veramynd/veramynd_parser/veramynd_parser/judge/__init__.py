"""Stage 6–7: alignment judge + evidence grounding."""

from .grounding import is_grounded
from .consistency import apply_consistency_to_judge_dir, apply_cross_lesson_consistency
from .models import AlignmentVerdict, JudgeBatchDraft, JudgeLlmDraft
from .pipeline import (
    DEFAULT_ESCALATE_MODEL,
    DEFAULT_JUDGE_MODEL,
    JUDGE_QUALITY_PROFILE,
    JudgeError,
    PROMPT_VERSION,
    judge_lesson_batch,
    judge_pair,
    judge_retrieve_file,
    write_judge_report,
)

__all__ = [
    "AlignmentVerdict",
    "DEFAULT_ESCALATE_MODEL",
    "DEFAULT_JUDGE_MODEL",
    "JUDGE_QUALITY_PROFILE",
    "JudgeBatchDraft",
    "JudgeError",
    "JudgeLlmDraft",
    "PROMPT_VERSION",
    "apply_consistency_to_judge_dir",
    "apply_cross_lesson_consistency",
    "is_grounded",
    "judge_lesson_batch",
    "judge_pair",
    "judge_retrieve_file",
    "write_judge_report",
]
