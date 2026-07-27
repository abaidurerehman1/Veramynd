"""OpenAI client for pedagogical normalization."""

from __future__ import annotations

import json
import os
import re
import time
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
# Cap for automatic truncation bumps (output tokens). v2 evidence is denser
# (qualifiers, actor examples, secondary foci); 16k was truncating long lessons.
_MAX_TOKENS_CAP = 32_768


def _next_max_tokens(current: int) -> int | None:
    """Return a higher budget after truncation, or ``None`` if already at the cap."""
    bumped = min(max(current * 2, current + 1024), _MAX_TOKENS_CAP)
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
    )


def _complete_openai(
    *,
    system: str,
    user: str,
    schema_model: type[T],
    model: str,
    api_key: str | None,
    max_tokens: int,
) -> T:
    try:
        from openai import APIConnectionError, APIStatusError, APITimeoutError, OpenAI, RateLimitError
    except ImportError as e:  # pragma: no cover
        raise LlmError(
            "openai package not installed. Run: pip install 'veramynd-parser[normalize]'"
        ) from e

    client = OpenAI(api_key=openai_api_key(api_key))
    schema = _strict_openai_schema(schema_model)
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]

    last_err: Exception | None = None
    for attempt in range(_MAX_ATTEMPTS):
        try:
            resp = client.chat.completions.create(
                model=model,
                temperature=0,
                max_tokens=max_tokens,
                response_format={
                    "type": "json_schema",
                    "json_schema": {
                        "name": schema_model.__name__,
                        "schema": schema,
                        "strict": True,
                    },
                },
                messages=messages,
            )
        except RateLimitError as e:
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

        choice = resp.choices[0]
        if choice.finish_reason == "length":
            nxt = _next_max_tokens(max_tokens)
            last_err = LlmError(
                f"response truncated at max_tokens={max_tokens} (finish_reason="
                f"'length') - the content was cut off mid-generation, not merely "
                f"malformed"
            )
            if nxt is None:
                raise LlmError(
                    f"OpenAI response truncated at max_tokens={max_tokens} and the "
                    f"cap ({_MAX_TOKENS_CAP}) is already reached; raise --max-tokens "
                    f"or shrink the lesson payload."
                ) from last_err
            print(
                f"OpenAI response truncated at max_tokens={max_tokens} - raising to "
                f"{nxt} and retrying (attempt {attempt + 1}/{_MAX_ATTEMPTS})...",
                flush=True,
            )
            max_tokens = nxt
            continue

        content = choice.message.content or ""
        try:
            return schema_model.model_validate(_extract_json_object(content))
        except (LlmError, ValueError, TypeError, json.JSONDecodeError) as e:
            last_err = e
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


# Backward-compatible aliases used by older tests / call sites during migration.
def default_model_for(_provider: str | None = None) -> str:
    return resolve_openai_model()
