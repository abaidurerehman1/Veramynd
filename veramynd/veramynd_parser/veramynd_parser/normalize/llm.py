"""OpenAI client for pedagogical normalization."""

from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)

# Default when OPENAI_MODEL / NormalizeConfig.model are unset.
DEFAULT_MODEL = "gpt-4.1-mini"

# Package root: veramynd_parser/ (contains pyproject.toml and .env)
_PACKAGE_ROOT = Path(__file__).resolve().parents[2]


class LlmError(RuntimeError):
    pass


class OutputTruncatedAtCap(LlmError):
    """Raised when the model hits its output-token cap and auto-raise is exhausted."""

    def __init__(self, *, provider: str, model: str, max_tokens: int, cap: int):
        self.provider = provider
        self.model = model
        self.max_tokens = max_tokens
        self.cap = cap
        super().__init__(
            f"{provider} response truncated at max_tokens={max_tokens} and the "
            f"cap ({cap}) is already reached for model {model}; enable "
            f"LLM_AUTO_RAISE / escalate model, or shrink the payload."
        )


def package_root() -> Path:
    """Directory that owns ``.env`` / ``.env.example`` for this package."""
    return _PACKAGE_ROOT


def load_dotenv() -> None:
    """Load ``project_root/.env`` only (never parent folders or cwd).

    Never overrides variables already present in the process environment.
    """
    try:
        from dotenv import load_dotenv as _load
    except ImportError:
        return

    path = _PACKAGE_ROOT / ".env"
    if path.is_file():
        _load(path, override=False)


def resolve_openai_model(explicit: str | None = None) -> str:
    """Model id: explicit config → OPENAI_MODEL env → DEFAULT_MODEL."""
    load_dotenv()
    if explicit and explicit.strip():
        return explicit.strip()
    env = (os.environ.get("OPENAI_MODEL") or "").strip()
    if env:
        return env
    return DEFAULT_MODEL


def openai_api_key(explicit: str | None = None) -> str:
    """Resolve OpenAI API key from config override or ``OPENAI_API_KEY`` env."""
    load_dotenv()
    if explicit and explicit.strip():
        return explicit.strip()
    key = (os.environ.get("OPENAI_API_KEY") or "").strip()
    if not key:
        raise LlmError(
            "OPENAI_API_KEY is not set. Copy .env.example to .env and set "
            "OPENAI_API_KEY (never pass keys on the command line)."
        )
    return key


def _extract_json_object(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", text, re.S)
        if not m:
            raise LlmError(f"Model did not return JSON: {text[:400]!r}")
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError as e:
            raise LlmError(f"Model returned malformed JSON: {e}") from e


def _strip_for_strict_schema(node: object) -> None:
    """Adjust a pydantic JSON schema for OpenAI Structured Outputs (strict mode)."""
    if isinstance(node, dict):
        node.pop("default", None)
        if node.get("type") == "object" or "properties" in node:
            node["additionalProperties"] = False
            props = node.get("properties")
            if props:
                node["required"] = list(props.keys())
                for sub in props.values():
                    _strip_for_strict_schema(sub)
        if "items" in node:
            _strip_for_strict_schema(node["items"])
        # Optional/union fields emit anyOf/oneOf/allOf branches whose object
        # arms need the same treatment, or strict mode 400s at request time.
        for combo_key in ("anyOf", "oneOf", "allOf"):
            for sub in node.get(combo_key) or []:
                _strip_for_strict_schema(sub)
        for defs_key in ("$defs", "definitions"):
            for sub in node.get(defs_key, {}).values():
                _strip_for_strict_schema(sub)


def _strict_schema(schema_model: type[BaseModel]) -> dict:
    schema = schema_model.model_json_schema()
    _strip_for_strict_schema(schema)
    return schema


# Public alias kept for tests / callers that imported the old name.
_strict_openai_schema = _strict_schema

_MAX_ATTEMPTS = 8
# Validation failures worth retrying before failing fast. Temperature-0 models
# get 2 (the request is deterministic — a bad response never improves);
# gpt-5/o-series omit temperature and sample, so retries genuinely can succeed.
_MAX_VALIDATION_ATTEMPTS_DETERMINISTIC = 2
_MAX_VALIDATION_ATTEMPTS_SAMPLED = 4
# Fallback output-token cap when the model id is unknown. Prefer
# ``output_token_cap(model)`` — gpt-4.1* is 32_768; o-series / gpt-5* higher.
_MAX_TOKENS_CAP = 32_768
# Default OpenAI model used when normalize hits the current model's output cap.
_DEFAULT_NORMALIZE_ESCALATE_MODEL = "o4-mini"
# Default Anthropic model used when judge hits the current model's output cap.
_DEFAULT_ANTHROPIC_ESCALATE_MODEL = "claude-opus-4-6"

# Models that reject ``max_tokens`` on chat.completions (require max_completion_tokens).
_MAX_COMPLETION_PREFIXES = ("gpt-5", "o1", "o3", "o4")

# 429 / RateLimitError codes that need user action — never sleep-and-retry.
_NON_RETRYABLE_OPENAI_CODES = frozenset(
    {
        "billing_not_active",
        "insufficient_quota",
    }
)
# Explicit rate-limit signals (informational; unknown 429s still retry).
_RETRYABLE_OPENAI_RATE_LIMIT_CODES = frozenset(
    {
        "rate_limit_exceeded",
        "requests_per_minute",
        "tokens_per_minute",
    }
)


def uses_max_completion_tokens(model: str) -> bool:
    """True when the chat Completions API requires ``max_completion_tokens``."""
    mid = (model or "").strip().lower()
    return any(mid.startswith(p) for p in _MAX_COMPLETION_PREFIXES)


def auto_raise_enabled() -> bool:
    """Whether truncate-at-cap should escalate / compact / split (default on)."""
    load_dotenv()
    raw = (os.environ.get("LLM_AUTO_RAISE") or "1").strip().lower()
    return raw not in ("0", "false", "no", "off")


def output_token_cap(model: str | None) -> int:
    """Provider max *output* tokens for ``model`` (conservative, publisher-agnostic)."""
    mid = (model or "").strip().lower()
    if not mid:
        return _MAX_TOKENS_CAP
    if any(mid.startswith(p) for p in ("o1", "o3", "o4", "gpt-5")):
        return 100_000
    if mid.startswith("claude"):
        # Claude 4.x / 3.7 class: 64k output; older Haiku-class stays lower.
        if any(
            tag in mid
            for tag in (
                "opus-4",
                "sonnet-4",
                "haiku-4",
                "4-5",
                "4-6",
                "3-7",
                "sonnet-3-7",
            )
        ):
            return 64_000
        return 8_192
    if mid.startswith("gpt-4o") and not mid.startswith("gpt-4.1"):
        return 16_384
    # gpt-4.1* and unknown chat models
    return _MAX_TOKENS_CAP


def resolve_normalize_escalate_model(current: str) -> str | None:
    """Higher-output OpenAI model when auto-raise is on; else ``None``."""
    if not auto_raise_enabled():
        return None
    load_dotenv()
    esc = (
        os.environ.get("NORMALIZE_ESCALATE_MODEL") or _DEFAULT_NORMALIZE_ESCALATE_MODEL
    ).strip()
    cur = (current or "").strip()
    if not esc or esc.lower() == cur.lower():
        return None
    if output_token_cap(esc) <= output_token_cap(cur):
        return None
    return esc


def resolve_anthropic_escalate_model(current: str) -> str | None:
    """Anthropic model to try after truncate-at-cap (judge path)."""
    if not auto_raise_enabled():
        return None
    load_dotenv()
    esc = (
        os.environ.get("LLM_ESCALATE_MODEL")
        or os.environ.get("JUDGE_ESCALATE_MODEL")
        or _DEFAULT_ANTHROPIC_ESCALATE_MODEL
    ).strip()
    cur = (current or "").strip()
    if not esc or esc.lower() == cur.lower():
        return None
    return esc


def build_chat_completion_request(
    *,
    model: str,
    messages: list[dict[str, str]],
    max_tokens: int,
    schema_model: type[BaseModel],
    temperature: float = 0,
) -> dict:
    """Build kwargs for ``client.chat.completions.create`` (single source of truth).

    All judge modes (batch / pair / escalation / fallback) and normalize paths
    must go through this helper so GPT-5-class models never receive ``max_tokens``.
    """
    schema = _strict_openai_schema(schema_model)
    kwargs: dict = {
        "model": model,
        "messages": messages,
        "response_format": {
            "type": "json_schema",
            "json_schema": {
                "name": schema_model.__name__,
                "schema": schema,
                "strict": True,
            },
        },
    }
    if uses_max_completion_tokens(model):
        kwargs["max_completion_tokens"] = max_tokens
        # Reasoning / GPT-5 chat models reject temperature on some accounts.
        # Omit it rather than sending an unsupported parameter.
    else:
        kwargs["max_tokens"] = max_tokens
        kwargs["temperature"] = temperature
    return kwargs


def _token_budget_from_request(kwargs: dict) -> int:
    if "max_completion_tokens" in kwargs:
        return int(kwargs["max_completion_tokens"])
    return int(kwargs["max_tokens"])


def _next_max_tokens(current: int, model: str | None = None) -> int | None:
    """Return a higher budget after truncation, or ``None`` if already at the cap."""
    cap = output_token_cap(model)
    bumped = min(max(current * 2, current + 1024), cap)
    if bumped <= current:
        return None
    return bumped


def structured_complete(
    *,
    system: str,
    user: str,
    schema_model: type[T],
    model: str | None = None,
    api_key: str | None = None,
    max_tokens: int = 2048,
    model_tracker: list[str] | None = None,
) -> T:
    """Call OpenAI and validate the response into ``schema_model``."""
    model_id = model or resolve_openai_model()
    return _complete_openai(
        system=system,
        user=user,
        schema_model=schema_model,
        model=model_id,
        api_key=api_key,
        max_tokens=max_tokens,
        model_tracker=model_tracker,
    )


def _complete_openai(
    *,
    system: str,
    user: str,
    schema_model: type[T],
    model: str,
    api_key: str | None,
    max_tokens: int,
    model_tracker: list[str] | None = None,
) -> T:
    try:
        from openai import APIConnectionError, APIStatusError, APITimeoutError, OpenAI, RateLimitError
    except ImportError as e:  # pragma: no cover
        raise LlmError(
            "openai package not installed. Run: pip install 'veramynd-parser[normalize]'"
        ) from e

    client = OpenAI(api_key=openai_api_key(api_key))
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]
    max_tokens = min(max(1, max_tokens), output_token_cap(model))
    escalated = False

    last_err: Exception | None = None
    validation_failures = 0
    for attempt in range(_MAX_ATTEMPTS):
        if model_tracker is not None:
            model_tracker.clear()
            model_tracker.append(model)
        request = build_chat_completion_request(
            model=model,
            messages=messages,
            max_tokens=max_tokens,
            schema_model=schema_model,
        )
        try:
            resp = client.chat.completions.create(**request)
        except RateLimitError as e:
            if is_non_retryable_openai_error(e):
                raise LlmError(format_non_retryable_openai_error(e)) from e
            last_err = e
            wait_s = _retry_wait_seconds(str(e), default=30.0)
            print(
                f"OpenAI rate limit - sleeping {wait_s:.0f}s "
                f"(attempt {attempt + 1}/{_MAX_ATTEMPTS})...",
                flush=True,
            )
            time.sleep(wait_s)
            continue
        except APIStatusError as e:
            last_err = e
            if is_non_retryable_openai_error(e):
                raise LlmError(format_non_retryable_openai_error(e)) from e
            if getattr(e, "status_code", None) in (429, 500, 502, 503, 529):
                wait_s = _retry_wait_seconds(str(e), default=20.0)
                print(
                    f"OpenAI HTTP {e.status_code} - sleeping {wait_s:.0f}s "
                    f"(attempt {attempt + 1}/{_MAX_ATTEMPTS})...",
                    flush=True,
                )
                time.sleep(wait_s)
                continue
            raise LlmError(f"OpenAI call failed: {e}") from e
        except (APIConnectionError, APITimeoutError, OSError, TimeoutError, json.JSONDecodeError) as e:
            raise LlmError(f"OpenAI call failed: {e}") from e

        record_openai_usage(resp, model)
        choice = resp.choices[0]
        if choice.finish_reason == "length":
            nxt = _next_max_tokens(max_tokens, model)
            last_err = LlmError(
                f"response truncated at max_tokens={max_tokens} (finish_reason="
                f"'length') - the content was cut off mid-generation, not merely "
                f"malformed"
            )
            if nxt is not None:
                print(
                    f"OpenAI response truncated at max_tokens={max_tokens} - raising to "
                    f"{nxt} and retrying (attempt {attempt + 1}/{_MAX_ATTEMPTS})...",
                    flush=True,
                )
                max_tokens = nxt
                validation_failures = 0
                continue
            esc = None if escalated else resolve_normalize_escalate_model(model)
            if esc is not None:
                new_cap = output_token_cap(esc)
                print(
                    f"AUTO-RAISE: normalize model {model} (cap {output_token_cap(model)}) "
                    f"→ {esc} (cap {new_cap}) after truncate-at-cap...",
                    flush=True,
                )
                model = esc
                escalated = True
                max_tokens = min(max(max_tokens * 2, max_tokens + 1024), new_cap)
                validation_failures = 0
                continue
            raise OutputTruncatedAtCap(
                provider="OpenAI",
                model=model,
                max_tokens=max_tokens,
                cap=output_token_cap(model),
            ) from last_err

        content = choice.message.content or ""
        try:
            return schema_model.model_validate(_extract_json_object(content))
        except (LlmError, ValueError, TypeError, json.JSONDecodeError) as e:
            last_err = e
            validation_failures += 1
            # Deterministic (temperature-0) requests can't improve on retry —
            # fail fast instead of burning up to 8 paid identical calls.
            # Sampled models (gpt-5/o-series, temperature omitted) get more
            # attempts since a re-draw genuinely can parse.
            cap = (
                _MAX_VALIDATION_ATTEMPTS_SAMPLED
                if uses_max_completion_tokens(model)
                else _MAX_VALIDATION_ATTEMPTS_DETERMINISTIC
            )
            if validation_failures >= cap:
                raise LlmError(
                    f"OpenAI response failed schema validation "
                    f"{validation_failures}x for model {model}: {e}"
                ) from e
            print(
                f"OpenAI response failed validation, retrying "
                f"(attempt {attempt + 1}/{_MAX_ATTEMPTS}): {e}",
                flush=True,
            )

    raise LlmError(f"OpenAI call did not succeed after {_MAX_ATTEMPTS} attempts: {last_err}")


def _retry_wait_seconds(message: str, *, default: float) -> float:
    m = re.search(r"try again in ([\d.]+)\s*s", message, re.I)
    if m:
        return min(float(m.group(1)) + 1.0, 300.0)
    m = re.search(r"Please try again in ([\d.]+)s", message, re.I)
    if m:
        return min(float(m.group(1)) + 1.0, 300.0)
    return default


def openai_error_code(exc: BaseException) -> str | None:
    """Best-effort provider ``code`` (or ``type``) from an OpenAI SDK exception."""
    for attr in ("code", "type"):
        value = getattr(exc, attr, None)
        if isinstance(value, str) and value.strip():
            return value.strip()

    body = getattr(exc, "body", None)
    if isinstance(body, dict):
        err = body.get("error") if isinstance(body.get("error"), dict) else body
        if isinstance(err, dict):
            for key in ("code", "type"):
                value = err.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()

    text = str(exc)
    for code in _NON_RETRYABLE_OPENAI_CODES | _RETRYABLE_OPENAI_RATE_LIMIT_CODES:
        if re.search(rf"\b{re.escape(code)}\b", text, re.I):
            return code
    return None


def is_non_retryable_openai_error(exc: BaseException) -> bool:
    """True for 429s that need user action (billing/quota), not transient rate limits."""
    code = (openai_error_code(exc) or "").strip().lower()
    if code in _NON_RETRYABLE_OPENAI_CODES:
        return True
    text = str(exc).lower()
    return any(c in text for c in _NON_RETRYABLE_OPENAI_CODES)


def format_non_retryable_openai_error(exc: BaseException) -> str:
    """Clear operator-facing message for billing/quota failures."""
    code = (openai_error_code(exc) or "").strip().lower()
    billing_url = "https://platform.openai.com/account/billing"
    if code == "billing_not_active" or "billing_not_active" in str(exc).lower():
        return (
            "OpenAI account billing is not active (billing_not_active). "
            f"Activate billing at {billing_url} — this error is not retryable."
        )
    if code == "insufficient_quota" or "insufficient_quota" in str(exc).lower():
        return (
            "OpenAI API quota exhausted (insufficient_quota). "
            f"Add credits or raise limits at {billing_url} — this error is not retryable."
        )
    return (
        f"OpenAI rejected the request with a non-retryable error "
        f"({code or 'unknown'}): {exc}"
    )


_NON_RETRYABLE_ANTHROPIC_MARKERS = (
    "authentication_error",
    "invalid x-api-key",
    "invalid api key",
    "permission_error",
    "credit balance is too low",
    "billing",
)


def anthropic_api_key(explicit: str | None = None) -> str:
    """Resolve Anthropic API key from override or ``ANTHROPIC_API_KEY`` env."""
    load_dotenv()
    if explicit and explicit.strip():
        return explicit.strip()
    key = (os.environ.get("ANTHROPIC_API_KEY") or "").strip()
    if not key:
        raise LlmError(
            "ANTHROPIC_API_KEY is not set. Copy .env.example to .env and set "
            "ANTHROPIC_API_KEY (never pass keys on the command line)."
        )
    return key


def is_non_retryable_anthropic_error(exc: BaseException) -> bool:
    """True for auth / billing failures that must not fall back to N pair calls."""
    text = str(exc).lower()
    status = getattr(exc, "status_code", None)
    if status in (401, 403):
        return True
    return any(m in text for m in _NON_RETRYABLE_ANTHROPIC_MARKERS)


def format_non_retryable_anthropic_error(exc: BaseException) -> str:
    return (
        "Anthropic API rejected the request (authentication or billing). "
        "Check ANTHROPIC_API_KEY and https://console.anthropic.com — "
        f"this error is not retryable. ({exc})"
    )


def is_non_retryable_llm_error(exc: BaseException) -> bool:
    """Billing/auth failures for OpenAI or Anthropic — do not retry or pair-fallback."""
    return is_non_retryable_openai_error(exc) or is_non_retryable_anthropic_error(exc)


# Anthropic prompt-cache breakpoint. Overlay + tool schema are identical
# across lessons; user payload (lesson + candidates) stays uncached.
_ANTHROPIC_CACHE_CONTROL = {"type": "ephemeral"}
_CACHE_WRITE_MULTIPLIER = 1.25
_CACHE_READ_MULTIPLIER = 0.1


def build_anthropic_message_request(
    *,
    model: str,
    system: str,
    user: str,
    max_tokens: int,
    schema_model: type[BaseModel],
    temperature: float = 0,
) -> dict:
    """Kwargs for ``Anthropic.messages.create`` (forced tool = structured JSON).

    Marks the shared system overlay and tool schema with prompt caching so
    later judge/normalize calls reuse those input tokens instead of re-billing
    the full overlay on every lesson.
    """
    schema = _strict_schema(schema_model)
    schema.pop("$schema", None)
    name = schema_model.__name__[:64]
    return {
        "model": model,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "system": [
            {
                "type": "text",
                "text": system,
                "cache_control": dict(_ANTHROPIC_CACHE_CONTROL),
            }
        ],
        "messages": [{"role": "user", "content": user}],
        "tools": [
            {
                "name": name,
                "description": "Return the structured result as tool input.",
                "input_schema": schema,
                "cache_control": dict(_ANTHROPIC_CACHE_CONTROL),
            }
        ],
        "tool_choice": {"type": "tool", "name": name},
    }


@dataclass
class AnthropicUsageTotals:
    calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cache_creation_input_tokens: int = 0
    cache_read_input_tokens: int = 0
    by_model: dict[str, dict[str, int]] = field(default_factory=dict)

    def record(
        self,
        model: str,
        input_tokens: int,
        output_tokens: int,
        cache_creation_input_tokens: int = 0,
        cache_read_input_tokens: int = 0,
    ) -> None:
        self.calls += 1
        self.input_tokens += input_tokens
        self.output_tokens += output_tokens
        self.cache_creation_input_tokens += cache_creation_input_tokens
        self.cache_read_input_tokens += cache_read_input_tokens
        bucket = self.by_model.setdefault(
            model,
            {
                "calls": 0,
                "input_tokens": 0,
                "output_tokens": 0,
                "cache_creation_input_tokens": 0,
                "cache_read_input_tokens": 0,
            },
        )
        bucket["calls"] += 1
        bucket["input_tokens"] += input_tokens
        bucket["output_tokens"] += output_tokens
        bucket["cache_creation_input_tokens"] += cache_creation_input_tokens
        bucket["cache_read_input_tokens"] += cache_read_input_tokens


_anthropic_usage = AnthropicUsageTotals()


@dataclass
class OpenAIUsageTotals:
    calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    by_model: dict[str, dict[str, int]] = field(default_factory=dict)

    def record(self, model: str, input_tokens: int, output_tokens: int = 0) -> None:
        self.calls += 1
        self.input_tokens += input_tokens
        self.output_tokens += output_tokens
        bucket = self.by_model.setdefault(
            model,
            {"calls": 0, "input_tokens": 0, "output_tokens": 0},
        )
        bucket["calls"] += 1
        bucket["input_tokens"] += input_tokens
        bucket["output_tokens"] += output_tokens


_openai_usage = OpenAIUsageTotals()


def reset_anthropic_usage() -> None:
    global _anthropic_usage
    _anthropic_usage = AnthropicUsageTotals()


def reset_openai_usage() -> None:
    global _openai_usage
    _openai_usage = OpenAIUsageTotals()


def anthropic_usage_totals() -> AnthropicUsageTotals:
    return _anthropic_usage


def openai_usage_totals() -> OpenAIUsageTotals:
    return _openai_usage


def _openai_model_rates(model: str) -> tuple[float, float]:
    """Return (input_usd_per_mtok, output_usd_per_mtok). Embeddings use input only."""
    name = (model or "").lower()
    if "text-embedding-3-large" in name:
        return 0.13, 0.0
    if "text-embedding-3-small" in name:
        return 0.02, 0.0
    if "gpt-4o-mini" in name:
        return 0.15, 0.60
    if "gpt-4o" in name:
        return 2.50, 10.0
    if "gpt-4.1-mini" in name or "gpt-4.1-nano" in name:
        return 0.40, 1.60
    if "gpt-4.1" in name:
        return 2.0, 8.0
    # Default chat ballpark (gpt-4o-class / unknown)
    return 2.50, 10.0


def _openai_cost_usd(*, model: str, input_tokens: int, output_tokens: int = 0) -> float:
    in_rate, out_rate = _openai_model_rates(model)
    return (input_tokens * in_rate + output_tokens * out_rate) / 1_000_000


def record_openai_usage(resp: object, model: str) -> None:
    usage = getattr(resp, "usage", None)
    if usage is None:
        return
    in_tok = int(
        getattr(usage, "prompt_tokens", None)
        or getattr(usage, "input_tokens", None)
        or 0
    )
    out_tok = int(
        getattr(usage, "completion_tokens", None)
        or getattr(usage, "output_tokens", None)
        or 0
    )
    # Embeddings often only set total_tokens
    if in_tok == 0 and out_tok == 0:
        in_tok = int(getattr(usage, "total_tokens", 0) or 0)
    if in_tok or out_tok:
        _openai_usage.record(model, in_tok, out_tok)


def openai_usage_report() -> dict[str, object]:
    totals = _openai_usage
    by_model: dict[str, dict[str, int | float]] = {}
    cost = 0.0
    for model, bucket in totals.by_model.items():
        model_cost = _openai_cost_usd(
            model=model,
            input_tokens=bucket["input_tokens"],
            output_tokens=bucket["output_tokens"],
        )
        cost += model_cost
        by_model[model] = {**bucket, "estimated_cost_usd": round(model_cost, 6)}
    return {
        "calls": totals.calls,
        "input_tokens": totals.input_tokens,
        "output_tokens": totals.output_tokens,
        "estimated_cost_usd": round(cost, 6),
        "by_model": by_model,
    }


def format_openai_usage_summary() -> str:
    totals = _openai_usage
    if totals.calls == 0:
        return "OpenAI usage: no API calls recorded"
    cost = 0.0
    lines = [
        (
            f"OpenAI usage: {totals.calls} call(s), "
            f"{totals.input_tokens:,} input + {totals.output_tokens:,} output tokens"
        )
    ]
    for model, bucket in sorted(totals.by_model.items()):
        model_cost = _openai_cost_usd(
            model=model,
            input_tokens=bucket["input_tokens"],
            output_tokens=bucket["output_tokens"],
        )
        cost += model_cost
        lines.append(
            f"  {model}: {bucket['calls']} call(s), "
            f"{bucket['input_tokens']:,} in + {bucket['output_tokens']:,} out "
            f"~ ${model_cost:.4f}"
        )
    lines.append(f"Estimated total cost: ${cost:.4f}")
    return "\n".join(lines)


def format_llm_usage_summary() -> str:
    """Combined OpenAI + Anthropic cost lines for CLI / pipeline logs."""
    parts = [format_openai_usage_summary(), format_anthropic_usage_summary()]
    o = float(openai_usage_report().get("estimated_cost_usd") or 0)
    a = float(anthropic_usage_report().get("estimated_cost_usd") or 0)
    if o or a:
        parts.append(f"Estimated total cost: ${o + a:.4f}")
    return "\n".join(parts)


def _anthropic_model_rates(model: str) -> tuple[float, float]:
    name = (model or "").lower()
    if "opus" in name:
        return 5.0, 25.0
    if "haiku" in name:
        return 1.0, 5.0
    return 3.0, 15.0


def _anthropic_cost_usd(
    *,
    model: str,
    input_tokens: int,
    output_tokens: int,
    cache_creation_input_tokens: int = 0,
    cache_read_input_tokens: int = 0,
) -> float:
    in_rate, out_rate = _anthropic_model_rates(model)
    return (
        input_tokens * in_rate
        + cache_creation_input_tokens * in_rate * _CACHE_WRITE_MULTIPLIER
        + cache_read_input_tokens * in_rate * _CACHE_READ_MULTIPLIER
        + output_tokens * out_rate
    ) / 1_000_000


def _record_anthropic_usage(resp: object, model: str) -> None:
    usage = getattr(resp, "usage", None)
    if usage is None:
        return
    in_tok = int(getattr(usage, "input_tokens", 0) or 0)
    out_tok = int(getattr(usage, "output_tokens", 0) or 0)
    cache_write = int(getattr(usage, "cache_creation_input_tokens", 0) or 0)
    cache_read = int(getattr(usage, "cache_read_input_tokens", 0) or 0)
    _anthropic_usage.record(
        model,
        in_tok,
        out_tok,
        cache_creation_input_tokens=cache_write,
        cache_read_input_tokens=cache_read,
    )


def anthropic_usage_report() -> dict[str, object]:
    totals = _anthropic_usage
    by_model: dict[str, dict[str, int | float]] = {}
    cost = 0.0
    for model, bucket in totals.by_model.items():
        model_cost = _anthropic_cost_usd(
            model=model,
            input_tokens=bucket["input_tokens"],
            output_tokens=bucket["output_tokens"],
            cache_creation_input_tokens=bucket["cache_creation_input_tokens"],
            cache_read_input_tokens=bucket["cache_read_input_tokens"],
        )
        cost += model_cost
        by_model[model] = {
            **bucket,
            "estimated_cost_usd": round(model_cost, 6),
        }
    return {
        "calls": totals.calls,
        "input_tokens": totals.input_tokens,
        "output_tokens": totals.output_tokens,
        "cache_creation_input_tokens": totals.cache_creation_input_tokens,
        "cache_read_input_tokens": totals.cache_read_input_tokens,
        "estimated_cost_usd": round(cost, 6),
        "by_model": by_model,
    }


def format_anthropic_usage_summary() -> str:
    totals = _anthropic_usage
    if totals.calls == 0:
        return "Anthropic usage: no API calls recorded"
    cost = 0.0
    lines = [
        (
            f"Anthropic usage: {totals.calls} call(s), "
            f"{totals.input_tokens:,} input + {totals.output_tokens:,} output tokens"
            f" (cache write {totals.cache_creation_input_tokens:,}, "
            f"cache read {totals.cache_read_input_tokens:,})"
        )
    ]
    for model, bucket in sorted(totals.by_model.items()):
        model_cost = _anthropic_cost_usd(
            model=model,
            input_tokens=bucket["input_tokens"],
            output_tokens=bucket["output_tokens"],
            cache_creation_input_tokens=bucket["cache_creation_input_tokens"],
            cache_read_input_tokens=bucket["cache_read_input_tokens"],
        )
        cost += model_cost
        lines.append(
            f"  {model}: {bucket['calls']} call(s), "
            f"{bucket['input_tokens']:,} in + {bucket['output_tokens']:,} out "
            f"cache_read={bucket['cache_read_input_tokens']:,} "
            f"~ ${model_cost:.4f}"
        )
    lines.append(f"Estimated total cost: ${cost:.4f}")
    return "\n".join(lines)


def _coerce_json_encoded_lists(payload: dict) -> dict:
    """Parse list fields that arrived as JSON strings (Anthropic tool quirk)."""
    out = dict(payload)
    for key, value in out.items():
        if not isinstance(value, str):
            continue
        text = value.strip()
        if not text.startswith("["):
            continue
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, list):
            out[key] = parsed
    return out


def _anthropic_tool_input(resp: object) -> dict:
    content = getattr(resp, "content", None) or []
    for block in content:
        if getattr(block, "type", None) == "tool_use":
            inp = getattr(block, "input", None)
            if isinstance(inp, dict):
                return _coerce_json_encoded_lists(inp)
            if inp is not None:
                return _coerce_json_encoded_lists(dict(inp))
    texts: list[str] = []
    for block in content:
        if getattr(block, "type", None) == "text":
            texts.append(getattr(block, "text", "") or "")
    if texts:
        extracted = _extract_json_object("\n".join(texts))
        return _coerce_json_encoded_lists(extracted)
    raise LlmError("Anthropic response had no tool_use JSON payload")


def structured_complete_anthropic(
    *,
    system: str,
    user: str,
    schema_model: type[T],
    model: str | None = None,
    api_key: str | None = None,
    max_tokens: int = 2048,
    model_tracker: list[str] | None = None,
) -> T:
    """Call Anthropic Messages API and validate into ``schema_model``."""
    if not (model or "").strip():
        raise LlmError("Anthropic judge call requires an explicit model id")
    return _complete_anthropic(
        system=system,
        user=user,
        schema_model=schema_model,
        model=model.strip(),
        api_key=api_key,
        max_tokens=max_tokens,
        model_tracker=model_tracker,
    )


def _complete_anthropic(
    *,
    system: str,
    user: str,
    schema_model: type[T],
    model: str,
    api_key: str | None,
    max_tokens: int,
    model_tracker: list[str] | None = None,
) -> T:
    try:
        from anthropic import (
            APIConnectionError,
            APIStatusError,
            APITimeoutError,
            Anthropic,
            RateLimitError,
        )
    except ImportError as e:  # pragma: no cover
        raise LlmError(
            "anthropic package not installed. Run: pip install 'veramynd-parser[judge]'"
        ) from e

    client = Anthropic(api_key=anthropic_api_key(api_key))
    max_tokens = min(max(1, max_tokens), output_token_cap(model))
    escalated = False
    last_err: Exception | None = None
    validation_failures = 0
    for attempt in range(_MAX_ATTEMPTS):
        if model_tracker is not None:
            model_tracker.clear()
            model_tracker.append(model)
        request = build_anthropic_message_request(
            model=model,
            system=system,
            user=user,
            max_tokens=max_tokens,
            schema_model=schema_model,
        )
        try:
            resp = client.messages.create(**request)
            _record_anthropic_usage(resp, model)
        except RateLimitError as e:
            if is_non_retryable_anthropic_error(e):
                raise LlmError(format_non_retryable_anthropic_error(e)) from e
            last_err = e
            wait_s = _retry_wait_seconds(str(e), default=30.0)
            print(
                f"Anthropic rate limit - sleeping {wait_s:.0f}s "
                f"(attempt {attempt + 1}/{_MAX_ATTEMPTS})...",
                flush=True,
            )
            time.sleep(wait_s)
            continue
        except APIStatusError as e:
            last_err = e
            if is_non_retryable_anthropic_error(e):
                raise LlmError(format_non_retryable_anthropic_error(e)) from e
            if getattr(e, "status_code", None) in (429, 500, 502, 503, 529):
                wait_s = _retry_wait_seconds(str(e), default=20.0)
                print(
                    f"Anthropic HTTP {e.status_code} - sleeping {wait_s:.0f}s "
                    f"(attempt {attempt + 1}/{_MAX_ATTEMPTS})...",
                    flush=True,
                )
                time.sleep(wait_s)
                continue
            raise LlmError(f"Anthropic call failed: {e}") from e
        except (APIConnectionError, APITimeoutError, OSError, TimeoutError) as e:
            raise LlmError(f"Anthropic call failed: {e}") from e

        if getattr(resp, "stop_reason", None) == "max_tokens":
            nxt = _next_max_tokens(max_tokens, model)
            last_err = LlmError(
                f"response truncated at max_tokens={max_tokens} (stop_reason="
                f"'max_tokens')"
            )
            if nxt is not None:
                print(
                    f"Anthropic response truncated at max_tokens={max_tokens} - raising "
                    f"to {nxt} and retrying (attempt {attempt + 1}/{_MAX_ATTEMPTS})...",
                    flush=True,
                )
                max_tokens = nxt
                validation_failures = 0
                continue
            esc = None if escalated else resolve_anthropic_escalate_model(model)
            if esc is not None and output_token_cap(esc) > output_token_cap(model):
                new_cap = output_token_cap(esc)
                print(
                    f"AUTO-RAISE: judge model {model} (cap {output_token_cap(model)}) "
                    f"→ {esc} (cap {new_cap}) after truncate-at-cap...",
                    flush=True,
                )
                model = esc
                escalated = True
                max_tokens = min(max(max_tokens * 2, max_tokens + 1024), new_cap)
                validation_failures = 0
                continue
            if esc is not None and not escalated:
                # Same output cap — still try once (denser model / different path).
                print(
                    f"AUTO-RAISE: judge model {model} → {esc} after truncate-at-cap "
                    f"(same output cap {output_token_cap(model)})...",
                    flush=True,
                )
                model = esc
                escalated = True
                validation_failures = 0
                continue
            raise OutputTruncatedAtCap(
                provider="Anthropic",
                model=model,
                max_tokens=max_tokens,
                cap=output_token_cap(model),
            ) from last_err

        try:
            return schema_model.model_validate(_anthropic_tool_input(resp))
        except (LlmError, ValueError, TypeError, json.JSONDecodeError) as e:
            last_err = e
            validation_failures += 1
            if validation_failures >= _MAX_VALIDATION_ATTEMPTS_DETERMINISTIC:
                raise LlmError(
                    f"Anthropic response failed schema validation "
                    f"{validation_failures}x for model {model}: {e}"
                ) from e
            print(
                f"Anthropic response failed validation, retrying "
                f"(attempt {attempt + 1}/{_MAX_ATTEMPTS}): {e}",
                flush=True,
            )

    raise LlmError(
        f"Anthropic call did not succeed after {_MAX_ATTEMPTS} attempts: {last_err}"
    )


# Backward-compatible aliases used by older tests / call sites during migration.
def default_model_for(_provider: str | None = None) -> str:
    return resolve_openai_model()
