"""Unit tests for normalize/llm.py (OpenAI only)."""

from __future__ import annotations

import sys
import types

import pytest
from pydantic import BaseModel

from veramynd_parser.normalize.llm import (
    LlmError,
    _extract_json_object,
    _retry_wait_seconds,
    _strict_openai_schema,
    openai_api_key,
    resolve_openai_model,
    structured_complete,
)


class _Target(BaseModel):
    code: str
    student_competencies: list[str] = []
    pedagogy_terms: list[str] = []
    instructional_text: str = ""
    prompt_version: str = "v1"
    provider: str = ""
    model: str = ""


def test_extract_json_object_plain():
    assert _extract_json_object('{"a": 1}') == {"a": 1}


def test_extract_json_object_strips_markdown_fences():
    assert _extract_json_object('```json\n{"a": 1}\n```') == {"a": 1}


def test_extract_json_object_recovers_embedded_object():
    assert _extract_json_object('Sure! Here you go: {"a": 1} — hope that helps.') == {"a": 1}


def test_extract_json_object_raises_llmerror_on_garbage():
    with pytest.raises(LlmError, match="did not return JSON"):
        _extract_json_object("not json at all")


def test_retry_wait_seconds_parses_provider_hint():
    assert _retry_wait_seconds("please try again in 12.5s", default=99) == 13.5


def test_retry_wait_seconds_falls_back_to_default():
    assert _retry_wait_seconds("no hint here", default=42.0) == 42.0


def test_retry_wait_seconds_is_capped_at_300():
    assert _retry_wait_seconds("try again in 10000s", default=1.0) == 300.0


def test_resolve_openai_model_explicit_wins(monkeypatch):
    monkeypatch.setenv("OPENAI_MODEL", "from-env")
    assert resolve_openai_model("gpt-explicit") == "gpt-explicit"


def test_resolve_openai_model_uses_env(monkeypatch):
    monkeypatch.setenv("OPENAI_MODEL", "gpt-from-env")
    assert resolve_openai_model(None) == "gpt-from-env"


def test_openai_api_key_requires_env(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    # Don't let package .env refill the process env during the assertion.
    monkeypatch.setattr("veramynd_parser.normalize.llm.load_dotenv", lambda: None)
    with pytest.raises(LlmError, match="OPENAI_API_KEY"):
        openai_api_key(None)


def test_strict_openai_schema_requires_every_property_and_forbids_extras():
    schema = _strict_openai_schema(_Target)
    assert schema["additionalProperties"] is False
    assert set(schema["required"]) == set(_Target.model_fields.keys())
    for prop in schema["properties"].values():
        assert "default" not in prop


def _make_openai_module(create_impl) -> types.ModuleType:
    mod = types.ModuleType("openai")

    class RateLimitError(Exception):
        pass

    class APIStatusError(Exception):
        def __init__(self, message="", status_code=500):
            super().__init__(message)
            self.status_code = status_code

    class APIConnectionError(Exception):
        pass

    class APITimeoutError(Exception):
        pass

    class _Choice:
        def __init__(self, content: str, finish_reason: str = "stop"):
            self.message = types.SimpleNamespace(content=content)
            self.finish_reason = finish_reason

    class _Resp:
        def __init__(self, content: str, finish_reason: str = "stop"):
            self.choices = [_Choice(content, finish_reason)]

    class _Completions:
        def create(self, **kwargs):
            return create_impl(**kwargs)

    class _Chat:
        def __init__(self):
            self.completions = _Completions()

    class OpenAI:
        def __init__(self, api_key: str | None = None) -> None:
            self.api_key = api_key
            self.chat = _Chat()

    mod.OpenAI = OpenAI
    mod.RateLimitError = RateLimitError
    mod.APIStatusError = APIStatusError
    mod.APIConnectionError = APIConnectionError
    mod.APITimeoutError = APITimeoutError
    mod._Resp = _Resp
    return mod


def _install_fake_openai(monkeypatch, create_impl):
    monkeypatch.setitem(sys.modules, "openai", _make_openai_module(create_impl))
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")


def test_openai_success(monkeypatch):
    mod = None

    def create(**kwargs):
        nonlocal mod
        mod = sys.modules["openai"]
        return mod._Resp(
            content='{"code": "G1M2U1L1", "student_competencies": ["do a thing"], '
            '"pedagogy_terms": [], "instructional_text": "", "prompt_version": "v1", '
            '"provider": "", "model": ""}'
        )

    _install_fake_openai(monkeypatch, create)
    result = structured_complete(
        system="sys", user="usr", schema_model=_Target, model="gpt-x"
    )
    assert result.code == "G1M2U1L1"


def test_openai_retries_on_validation_failure_then_succeeds(monkeypatch):
    calls = {"n": 0}
    mod_holder = {}

    def create(**kwargs):
        calls["n"] += 1
        mod = sys.modules["openai"]
        mod_holder["mod"] = mod
        if calls["n"] == 1:
            return mod._Resp(content='{"code": 123}')  # invalid type
        return mod._Resp(
            content='{"code": "G1M2U1L1", "student_competencies": [], '
            '"pedagogy_terms": [], "instructional_text": "", "prompt_version": "v1", '
            '"provider": "", "model": ""}'
        )

    _install_fake_openai(monkeypatch, create)
    result = structured_complete(
        system="sys", user="usr", schema_model=_Target, model="gpt-x"
    )
    assert result.code == "G1M2U1L1"
    assert calls["n"] == 2


def test_openai_truncation_is_detected(monkeypatch):
    seen_max_tokens: list[int] = []

    def create(**kwargs):
        seen_max_tokens.append(kwargs["max_tokens"])
        mod = sys.modules["openai"]
        return mod._Resp(content='{"code": "x"', finish_reason="length")

    _install_fake_openai(monkeypatch, create)
    with pytest.raises(LlmError, match="truncated"):
        structured_complete(
            system="sys", user="usr", schema_model=_Target, model="gpt-x", max_tokens=8
        )
    # Retries must raise the budget, not spin on the same max_tokens.
    assert seen_max_tokens[0] == 8
    assert seen_max_tokens[1] > 8
    assert seen_max_tokens == sorted(seen_max_tokens)


def test_openai_truncation_succeeds_after_budget_bump(monkeypatch):
    def create(**kwargs):
        mod = sys.modules["openai"]
        if kwargs["max_tokens"] < 100:
            return mod._Resp(content='{"code": "x"', finish_reason="length")
        return mod._Resp(
            content=(
                '{"code": "G1M2U1L1", "student_competencies": [], '
                '"pedagogy_terms": [], "instructional_text": "ok", '
                '"prompt_version": "v1", "provider": "", "model": ""}'
            ),
            finish_reason="stop",
        )

    _install_fake_openai(monkeypatch, create)
    result = structured_complete(
        system="sys", user="usr", schema_model=_Target, model="gpt-x", max_tokens=8
    )
    assert result.code == "G1M2U1L1"
