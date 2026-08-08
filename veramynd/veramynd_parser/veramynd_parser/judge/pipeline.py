"""Alignment judge: lesson × standard(s) → verdicts + grounding.

Enterprise K–12 default:
  - **Batch** first (one OpenAI call per lesson) for throughput
  - **Escalate** hard/borderline cases with a stronger model (on by default)
  - **Pair fallback** if batch JSON is invalid
  - **Grounding** rejects ungrounded positive claims

Pass ``escalate=False`` / ``--no-escalate`` for cheap smoke runs.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, Callable

from ..normalize.cache import ContentAddressedCache, canonical_json
from ..normalize.llm import (
    LlmError,
    is_non_retryable_openai_error,
    load_dotenv,
    structured_complete,
)
from ..paths import resolve_package_relative
from ..text_utils import atomic_write_text
from .grounding import grounding_note, is_grounded
from .io import (
    JudgeIoError,
    load_lesson_context,
    load_retrieve_candidates,
    load_standard_raw_text,
)
from .models import (
    AlignmentVerdict,
    CachedBatchVerdicts,
    JudgeBatchDraft,
    JudgeBatchItem,
    JudgeLlmDraft,
)

PROMPT_VERSION = "align_judge.v1.1"
BATCH_PROMPT_VERSION = "align_judge.batch.v1"
DEFAULT_JUDGE_MODEL = "gpt-4.1"
DEFAULT_ESCALATE_MODEL = "gpt-5"
JUDGE_SCHEMA_VERSION = "1.0-judge"
JUDGE_QUALITY_PROFILE = "enterprise_k12"
DEFAULT_BATCH_MAX_TOKENS = 8192
_PROMPT_PATH = Path(__file__).resolve().parent.parent / "prompts" / "align_judge_v1.md"
_BATCH_ADDENDUM_PATH = (
    Path(__file__).resolve().parent.parent / "prompts" / "align_judge_batch_addendum.md"
)
_DEFAULT_CACHE = ".normalize_cache/judge"

log = logging.getLogger(__name__)


class JudgeError(RuntimeError):
    pass


class JudgeIncompleteError(JudgeError):
    """Raised when some candidates failed; ``report`` may still be inspected."""

    def __init__(self, message: str, report: dict[str, Any]) -> None:
        super().__init__(message)
        self.report = report


def resolve_judge_model(explicit: str | None = None) -> str:
    load_dotenv()
    if explicit and explicit.strip():
        return explicit.strip()
    env = (os.environ.get("JUDGE_MODEL") or "").strip()
    if env:
        return env
    return DEFAULT_JUDGE_MODEL


def resolve_escalate_model(explicit: str | None = None) -> str:
    load_dotenv()
    if explicit and explicit.strip():
        return explicit.strip()
    env = (os.environ.get("JUDGE_ESCALATE_MODEL") or "").strip()
    if env:
        return env
    return DEFAULT_ESCALATE_MODEL


def _load_prompt() -> str:
    if not _PROMPT_PATH.is_file():
        raise JudgeError(f"judge prompt missing: {_PROMPT_PATH}")
    return _PROMPT_PATH.read_text(encoding="utf-8")


def _load_batch_prompt() -> str:
    base = _load_prompt()
    if not _BATCH_ADDENDUM_PATH.is_file():
        raise JudgeError(f"batch judge addendum missing: {_BATCH_ADDENDUM_PATH}")
    return base.rstrip() + "\n\n" + _BATCH_ADDENDUM_PATH.read_text(encoding="utf-8")


def _resolve_cache_dir(cache_dir: Path | str | None) -> Path:
    raw = cache_dir if cache_dir is not None else _DEFAULT_CACHE
    return Path(resolve_package_relative(str(raw)))


def _should_escalate(draft: JudgeLlmDraft) -> bool:
    """Enterprise cascade: re-judge borderline / hard / weakly evidenced claims."""
    if draft.matched_status == "partial":
        return True
    if draft.confidence in {"low", "medium"}:
        return True
    if draft.matched_status in {"full", "partial"} and not (draft.evidence or "").strip():
        return True
    if draft.matched_status == "full" and (
        not draft.clauses or any(not c.met for c in draft.clauses)
    ):
        # A "full" claim with an unmet clause — or no clause analysis at all —
        # is internally inconsistent; exactly what escalation should re-check.
        return True
    return False


def _call_judge(
    *,
    system: str,
    user: str,
    model: str,
    api_key: str | None,
    max_tokens: int,
    complete_fn: Callable[..., JudgeLlmDraft] | None,
) -> JudgeLlmDraft:
    encode = complete_fn or structured_complete
    try:
        return encode(
            system=system,
            user=user,
            schema_model=JudgeLlmDraft,
            model=model,
            api_key=api_key,
            max_tokens=max_tokens,
        )
    except LlmError as e:
        raise JudgeError(str(e)) from e


def _call_judge_batch(
    *,
    system: str,
    user: str,
    model: str,
    api_key: str | None,
    max_tokens: int,
    complete_fn: Callable[..., JudgeBatchDraft] | None,
) -> JudgeBatchDraft:
    encode = complete_fn or structured_complete
    try:
        return encode(
            system=system,
            user=user,
            schema_model=JudgeBatchDraft,
            model=model,
            api_key=api_key,
            max_tokens=max_tokens,
        )
    except LlmError as e:
        raise JudgeError(str(e)) from e


def _finalize_verdict(
    *,
    resource_id: str,
    standard_code: str,
    standard_raw_text: str,
    lesson_raw_text: str,
    draft: JudgeLlmDraft,
    used_model: str,
    escalated: bool,
    retrieval: dict[str, Any] | None,
    prompt_version: str,
) -> AlignmentVerdict:
    status = draft.matched_status
    evidence = (draft.evidence or "").strip()
    confidence = draft.confidence
    rationale = draft.rationale

    if status == "none":
        # No evidence is required for a "none" verdict: drop any quote the
        # model returned and note exactly that. The note must never claim a
        # quote was "found in lesson raw text" for a check that never ran.
        evidence = ""
        grounded = True
        gnote = grounding_note(evidence, grounded=True, allow_empty=True)
    else:
        grounded = is_grounded(evidence, lesson_raw_text, allow_empty=False)
        gnote = grounding_note(evidence, grounded=grounded, allow_empty=False)
        if not grounded:
            status = "none"
            confidence = "low"
            rationale = (
                f"{rationale} [REJECTED: evidence missing or not found in "
                "lesson raw text]"
            )

    return AlignmentVerdict(
        schema_version=JUDGE_SCHEMA_VERSION,
        resource_id=resource_id,
        standard_code=standard_code,
        matched_status=status,
        clauses=draft.clauses,
        evidence=evidence,
        evidence_page=draft.evidence_page,
        confidence=confidence,
        rationale=rationale,
        grounded=grounded,
        grounding_note=gnote,
        prompt_version=prompt_version,
        judge_model=used_model,
        escalated=escalated,
        retrieval=dict(retrieval or {}),
        standard_raw_text=standard_raw_text,
    )


def judge_pair(
    *,
    resource_id: str,
    lesson_raw_text: str,
    standard: dict[str, Any],
    retrieval: dict[str, Any] | None = None,
    model: str | None = None,
    escalate_model: str | None = None,
    escalate: bool = True,
    api_key: str | None = None,
    max_tokens: int = 2048,
    cache_dir: Path | str | None = None,
    use_cache: bool = True,
    complete_fn: Callable[..., JudgeLlmDraft] | None = None,
) -> AlignmentVerdict:
    """Judge one (lesson, standard) pair. One standard per LLM call.

    Enterprise default ``escalate=True`` re-judges borderline cases with the
    escalate model (partial / low|medium confidence / empty evidence).
    """
    code = (standard.get("standard_code") or "").strip()
    raw = (standard.get("raw_text") or "").strip()
    if not code or not raw:
        raise JudgeError("standard_code and raw_text are required")
    lesson = (lesson_raw_text or "").strip()
    if not lesson:
        raise JudgeError("empty lesson_raw_text")

    model_id = resolve_judge_model(model)
    system = _load_prompt()
    payload = {
        "resource_id": resource_id,
        "standard_code": code,
        "standard_raw_text": raw,
        "standard_competency": (standard.get("competency_statement") or "").strip(),
        "domain_primary": (standard.get("domain_primary") or "").strip(),
        "skill_clauses": standard.get("skill_clauses") or [],
        "lesson_raw_text": lesson,
    }
    user = (
        "Judge this single lesson–standard pair.\n\n"
        f"<<<JSON\n{json.dumps(payload, ensure_ascii=False, indent=2)}\nJSON>>>"
    )

    cache: ContentAddressedCache | None = None
    cache_key = ""
    esc_id = resolve_escalate_model(escalate_model)
    if use_cache and complete_fn is None:
        cache = ContentAddressedCache(_resolve_cache_dir(cache_dir))
        cache_key = ContentAddressedCache.key(
            PROMPT_VERSION,
            "openai",
            model_id,
            f"escalate={int(bool(escalate))}",
            esc_id if escalate else "",
            system,
            canonical_json(payload),
        )
        hit = cache.get(cache_key, AlignmentVerdict)
        if hit is not None:
            # The cache key excludes retrieval scores by design (retrieval
            # must not bias judging) — so re-stamp the CURRENT run's scores
            # rather than persisting the cached run's stale provenance.
            return hit.model_copy(update={"retrieval": dict(retrieval or {})})

    draft = _call_judge(
        system=system,
        user=user,
        model=model_id,
        api_key=api_key,
        max_tokens=max_tokens,
        complete_fn=complete_fn,
    )
    used_model = model_id
    escalated = False

    if (
        escalate
        and complete_fn is None
        and _should_escalate(draft)
        and esc_id != model_id
    ):
        draft = _call_judge(
            system=system,
            user=user,
            model=esc_id,
            api_key=api_key,
            max_tokens=max_tokens,
            complete_fn=None,
        )
        used_model = esc_id
        escalated = True

    verdict = _finalize_verdict(
        resource_id=resource_id,
        standard_code=code,
        standard_raw_text=raw,
        lesson_raw_text=lesson,
        draft=draft,
        used_model=used_model,
        escalated=escalated,
        retrieval=retrieval,
        prompt_version=PROMPT_VERSION,
    )

    if cache is not None and cache_key:
        cache.put(cache_key, verdict)
    return verdict


def _retrieval_meta(cand: dict[str, Any]) -> dict[str, Any]:
    return {
        "rrf_score": cand.get("rrf_score"),
        "dense_rank": cand.get("dense_rank"),
        "bm25_rank": cand.get("bm25_rank"),
        "dense_score": cand.get("dense_score"),
        "bm25_score": cand.get("bm25_score"),
        "rerank_score": cand.get("rerank_score"),
    }


def _validate_batch_results(
    draft: JudgeBatchDraft, expected_codes: list[str]
) -> dict[str, JudgeBatchItem]:
    """Map standard_code → item; raise if codes missing/extra/duplicate."""
    by_code: dict[str, JudgeBatchItem] = {}
    for item in draft.results:
        code = (item.standard_code or "").strip()
        if not code:
            raise JudgeError("batch result missing standard_code")
        if code in by_code:
            raise JudgeError(f"batch result duplicate standard_code: {code}")
        by_code[code] = item

    expected = set(expected_codes)
    got = set(by_code)
    missing = sorted(expected - got)
    extra = sorted(got - expected)
    if missing or extra:
        parts: list[str] = []
        if missing:
            parts.append(f"missing={missing}")
        if extra:
            parts.append(f"extra={extra}")
        raise JudgeError("batch result code mismatch: " + "; ".join(parts))
    return by_code


def judge_lesson_batch(
    *,
    resource_id: str,
    lesson_raw_text: str,
    standards: list[dict[str, Any]],
    retrieval_by_code: dict[str, dict[str, Any]] | None = None,
    model: str | None = None,
    escalate_model: str | None = None,
    escalate: bool = True,
    api_key: str | None = None,
    max_tokens: int = DEFAULT_BATCH_MAX_TOKENS,
    cache_dir: Path | str | None = None,
    use_cache: bool = True,
    complete_fn: Callable[..., JudgeBatchDraft] | None = None,
    pair_complete_fn: Callable[..., JudgeLlmDraft] | None = None,
) -> list[AlignmentVerdict]:
    """Judge all standards for one lesson in a single LLM call.

    Enterprise default escalates borderline batch items via a targeted pair
    call on the escalate model. On invalid batch JSON, raises ``JudgeError``
    so the caller can fall back to per-pair judging.
    """
    lesson = (lesson_raw_text or "").strip()
    if not lesson:
        raise JudgeError("empty lesson_raw_text")
    if not standards:
        raise JudgeError("no standards to judge")

    prepared: list[dict[str, Any]] = []
    codes: list[str] = []
    for std in standards:
        code = (std.get("standard_code") or "").strip()
        raw = (std.get("raw_text") or "").strip()
        if not code or not raw:
            raise JudgeError("standard_code and raw_text are required for every standard")
        codes.append(code)
        prepared.append(
            {
                "standard_code": code,
                "standard_raw_text": raw,
                "standard_competency": (std.get("competency_statement") or "").strip(),
                "domain_primary": (std.get("domain_primary") or "").strip(),
                "skill_clauses": std.get("skill_clauses") or [],
            }
        )

    if len(set(codes)) != len(codes):
        raise JudgeError("duplicate standard_code in batch input")

    model_id = resolve_judge_model(model)
    system = _load_batch_prompt()
    payload = {
        "resource_id": resource_id,
        "lesson_raw_text": lesson,
        "candidates": prepared,
    }
    user = (
        "Judge this lesson against every candidate standard independently.\n"
        f"Return exactly {len(codes)} results covering codes: {codes}.\n\n"
        f"<<<JSON\n{json.dumps(payload, ensure_ascii=False, indent=2)}\nJSON>>>"
    )

    cache: ContentAddressedCache | None = None
    cache_key = ""
    esc_id = resolve_escalate_model(escalate_model)
    if use_cache and complete_fn is None:
        cache = ContentAddressedCache(_resolve_cache_dir(cache_dir))
        cache_key = ContentAddressedCache.key(
            BATCH_PROMPT_VERSION,
            "openai",
            model_id,
            f"escalate={int(bool(escalate))}",
            esc_id if escalate else "",
            system,
            canonical_json(payload),
        )
        hit = cache.get(cache_key, CachedBatchVerdicts)
        if hit is not None:
            # Same as the pair path: refresh retrieval provenance to the
            # current run's scores instead of serving the cached run's.
            rbc = retrieval_by_code or {}
            return [
                v.model_copy(
                    update={"retrieval": dict(rbc.get(v.standard_code) or {})}
                )
                for v in hit.verdicts
            ]

    print(
        f"  batch-judging {len(codes)} standards in one call "
        f"(model={model_id}, max_tokens={max_tokens})...",
        flush=True,
    )
    batch_draft = _call_judge_batch(
        system=system,
        user=user,
        model=model_id,
        api_key=api_key,
        max_tokens=max_tokens,
        complete_fn=complete_fn,
    )
    by_code = _validate_batch_results(batch_draft, codes)

    retrieval_by_code = retrieval_by_code or {}
    std_by_code = {s["standard_code"]: s for s in standards}
    verdicts: list[AlignmentVerdict] = []
    for code in codes:
        item = by_code[code]
        draft = item.to_draft()
        used_model = model_id
        escalated = False
        std = std_by_code[code]
        raw = (std.get("raw_text") or "").strip()

        if (
            escalate
            and complete_fn is None
            and _should_escalate(draft)
            and esc_id != model_id
        ):
            # Quality path: hard cases only — one targeted pair call.
            print(f"    escalate {code} ({draft.matched_status}/{draft.confidence})...", flush=True)
            escalated_v = judge_pair(
                resource_id=resource_id,
                lesson_raw_text=lesson,
                standard=std,
                retrieval=retrieval_by_code.get(code),
                model=esc_id,
                escalate=False,
                api_key=api_key,
                max_tokens=min(max_tokens, 4096),
                cache_dir=cache_dir,
                use_cache=use_cache,
                complete_fn=pair_complete_fn,
            )
            # Mark escalate provenance while keeping grounded finalize from pair.
            escalated_v = escalated_v.model_copy(
                update={
                    "escalated": True,
                    "judge_model": esc_id,
                    "prompt_version": PROMPT_VERSION,
                }
            )
            verdicts.append(escalated_v)
            continue

        verdicts.append(
            _finalize_verdict(
                resource_id=resource_id,
                standard_code=code,
                standard_raw_text=raw,
                lesson_raw_text=lesson,
                draft=draft,
                used_model=used_model,
                escalated=escalated,
                retrieval=retrieval_by_code.get(code),
                prompt_version=BATCH_PROMPT_VERSION,
            )
        )

    if cache is not None and cache_key:
        cache.put(cache_key, CachedBatchVerdicts(verdicts=verdicts))
    return verdicts


def _build_report(
    *,
    resource_id: str,
    source: str,
    retrieve_file: Path | str,
    std_dir: Path,
    model: str | None,
    escalate: bool,
    escalate_model: str | None,
    candidates: list[dict[str, Any]],
    verdicts: list[AlignmentVerdict],
    failed: list[dict[str, str]],
    judge_mode: str,
) -> dict[str, Any]:
    by_status = {"full": 0, "partial": 0, "none": 0}
    positive = 0
    positive_grounded = 0
    for v in verdicts:
        by_status[v.matched_status] = by_status.get(v.matched_status, 0) + 1
        if v.matched_status in {"full", "partial"}:
            positive += 1
            if v.grounded:
                positive_grounded += 1

    return {
        "schema_version": JUDGE_SCHEMA_VERSION,
        "quality_profile": JUDGE_QUALITY_PROFILE,
        "prompt_version": (
            BATCH_PROMPT_VERSION if judge_mode == "batch" else PROMPT_VERSION
        ),
        "judge_mode": judge_mode,
        "resource_id": resource_id,
        "lesson_source": source,
        "retrieve_file": str(retrieve_file),
        "standards_dir": str(std_dir),
        "judge_model": resolve_judge_model(model),
        "escalate": escalate,
        "escalate_model": resolve_escalate_model(escalate_model) if escalate else None,
        "candidate_count": len(candidates),
        "judged": len(verdicts),
        "failed": failed,
        "complete": len(failed) == 0 and len(verdicts) == len(candidates),
        "by_status": by_status,
        "grounding_rate": (positive_grounded / positive) if positive else None,
        "grounding_positive_n": positive,
        "verdicts": [v.to_dict() for v in verdicts],
    }


def judge_retrieve_file(
    *,
    retrieve_file: Path | str,
    standards_dir: Path | str,
    lesson_file: Path | str | None = None,
    chunk_file: Path | str | None = None,
    model: str | None = None,
    escalate_model: str | None = None,
    escalate: bool = True,
    api_key: str | None = None,
    max_tokens: int | None = None,
    cache_dir: Path | str | None = None,
    use_cache: bool = True,
    limit: int | None = None,
    batch: bool = True,
    batch_fallback_pair: bool = True,
    complete_fn: Callable[..., JudgeLlmDraft] | None = None,
    batch_complete_fn: Callable[..., JudgeBatchDraft] | None = None,
) -> dict[str, Any]:
    """Judge all candidates in a retrieve JSON against one lesson's raw text.

    Enterprise K–12 defaults:
      - ``batch=True`` — one LLM call for all candidates
      - ``escalate=True`` — re-judge partial / low|medium / empty-evidence cases
      - ``batch_fallback_pair=True`` — pair mode if batch JSON is invalid
    """
    try:
        resource_id, lesson_raw, source = load_lesson_context(
            lesson_file=lesson_file, chunk_file=chunk_file
        )
        candidates = load_retrieve_candidates(retrieve_file)
    except JudgeIoError as e:
        raise JudgeError(str(e)) from e

    if limit is not None:
        if limit < 1:
            raise JudgeError(f"limit must be >= 1, got {limit}")
        candidates = candidates[:limit]

    std_dir = Path(standards_dir)
    if not std_dir.is_dir():
        raise JudgeError(f"standards dir not found: {std_dir}")

    # Injected pair mock ⇒ pair mode unless an explicit batch mock is provided.
    use_batch = bool(batch)
    if complete_fn is not None and batch_complete_fn is None:
        use_batch = False

    standards: list[dict[str, Any]] = []
    retrieval_by_code: dict[str, dict[str, Any]] = {}
    load_failed: list[dict[str, str]] = []
    for cand in candidates:
        code = cand["standard_code"]
        try:
            std = load_standard_raw_text(std_dir, code)
            standards.append(std)
            retrieval_by_code[code] = _retrieval_meta(cand)
        except JudgeIoError as e:
            load_failed.append({"standard_code": code, "error": str(e)})
            print(f"    ERROR load {code}: {e}", flush=True)

    verdicts: list[AlignmentVerdict] = []
    failed: list[dict[str, str]] = list(load_failed)
    judge_mode = "pair"

    if use_batch and standards:
        tokens = DEFAULT_BATCH_MAX_TOKENS if max_tokens is None else max_tokens
        try:
            verdicts = judge_lesson_batch(
                resource_id=resource_id,
                lesson_raw_text=lesson_raw,
                standards=standards,
                retrieval_by_code=retrieval_by_code,
                model=model,
                escalate_model=escalate_model,
                escalate=escalate,
                api_key=api_key,
                max_tokens=tokens,
                cache_dir=cache_dir,
                use_cache=use_cache,
                complete_fn=batch_complete_fn,
                pair_complete_fn=complete_fn,
            )
            judge_mode = "batch"
        except (JudgeError, LlmError) as e:
            # Billing/quota need operator action — do not thrash pair fallback.
            if is_non_retryable_openai_error(e):
                raise
            log.warning("batch judge failed for %s: %s", resource_id, e)
            print(f"  WARN batch judge failed: {e}", flush=True)
            if not batch_fallback_pair:
                failed.append({"standard_code": "*", "error": f"batch: {e}"})
            else:
                print("  falling back to per-pair judge...", flush=True)
                use_batch = False
                verdicts = []

    if not use_batch or (not verdicts and batch_fallback_pair and standards):
        judge_mode = "pair"
        tokens = 2048 if max_tokens is None else max_tokens
        for i, std in enumerate(standards, start=1):
            code = std["standard_code"]
            print(f"  [{i}/{len(standards)}] judging {code}...", flush=True)
            try:
                v = judge_pair(
                    resource_id=resource_id,
                    lesson_raw_text=lesson_raw,
                    standard=std,
                    retrieval=retrieval_by_code.get(code),
                    model=model,
                    escalate_model=escalate_model,
                    escalate=escalate,
                    api_key=api_key,
                    max_tokens=tokens,
                    cache_dir=cache_dir,
                    use_cache=use_cache,
                    complete_fn=complete_fn,
                )
                verdicts.append(v)
            except (JudgeError, JudgeIoError, LlmError) as e:
                if is_non_retryable_openai_error(e):
                    raise
                failed.append({"standard_code": code, "error": str(e)})
                print(f"    ERROR {code}: {e}", flush=True)

    report = _build_report(
        resource_id=resource_id,
        source=source,
        retrieve_file=retrieve_file,
        std_dir=std_dir,
        model=model,
        escalate=escalate,
        escalate_model=escalate_model,
        candidates=candidates,
        verdicts=verdicts,
        failed=failed,
        judge_mode=judge_mode,
    )
    if failed:
        raise JudgeIncompleteError(
            f"judge incomplete for {resource_id}: {len(failed)}/{len(candidates)} "
            f"candidates failed: "
            + "; ".join(f"{f['standard_code']}: {f['error']}" for f in failed[:5]),
            report,
        )
    return report


def write_judge_report(report: dict[str, Any], out: Path | str) -> Path:
    path = Path(out)
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(path, json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    return path


__all__ = [
    "BATCH_PROMPT_VERSION",
    "DEFAULT_BATCH_MAX_TOKENS",
    "DEFAULT_ESCALATE_MODEL",
    "DEFAULT_JUDGE_MODEL",
    "JUDGE_QUALITY_PROFILE",
    "JUDGE_SCHEMA_VERSION",
    "JudgeError",
    "JudgeIncompleteError",
    "PROMPT_VERSION",
    "judge_lesson_batch",
    "judge_pair",
    "judge_retrieve_file",
    "resolve_escalate_model",
    "resolve_judge_model",
    "write_judge_report",
]
