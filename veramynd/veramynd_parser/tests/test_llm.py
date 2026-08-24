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
    _token_budget_from_request,
    build_chat_completion_request,
    format_non_retryable_openai_error,
    is_non_retryable_openai_error,
    openai_api_key,
    openai_error_code,
    resolve_openai_model,
    structured_complete,
    uses_max_completion_tokens,
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


def test_openai_error_code_from_attr_and_body():
    class E(Exception):
        pass

    e = E("x")
    e.code = "billing_not_active"
    assert openai_error_code(e) == "billing_not_active"

    e2 = E("x")
    e2.body = {"error": {"code": "insufficient_quota", "type": "insufficient_quota"}}
    assert openai_error_code(e2) == "insufficient_quota"

    e3 = E("Error code: 429 - rate_limit_exceeded")
    assert openai_error_code(e3) == "rate_limit_exceeded"


def test_is_non_retryable_openai_error_codes():
    class E(Exception):
        pass

    billing = E("billing inactive")
    billing.code = "billing_not_active"
    assert is_non_retryable_openai_error(billing) is True

    quota = E("quota")
    quota.code = "insufficient_quota"
    assert is_non_retryable_openai_error(quota) is True

    rate = E("slow down")
    rate.code = "rate_limit_exceeded"
    assert is_non_retryable_openai_error(rate) is False

    rpm = E("rpm")
    rpm.code = "requests_per_minute"
    assert is_non_retryable_openai_error(rpm) is False


def test_format_non_retryable_openai_error_messages():
    class E(Exception):
        pass

    billing = E("inactive")
    billing.code = "billing_not_active"
    msg = format_non_retryable_openai_error(billing)
    assert "billing_not_active" in msg
    assert "not retryable" in msg

    quota = E("out")
    quota.code = "insufficient_quota"
    msg = format_non_retryable_openai_error(quota)
    assert "insufficient_quota" in msg
    assert "not retryable" in msg


def test_openai_fails_fast_on_billing_not_active(monkeypatch):
    sleeps: list[float] = []
    calls = {"n": 0}

    def create(**kwargs):
        calls["n"] += 1
        mod = sys.modules["openai"]
        raise mod.RateLimitError(
            "Your account is not active",
            code="billing_not_active",
            body={"error": {"code": "billing_not_active", "type": "billing_not_active"}},
        )

    _install_fake_openai(monkeypatch, create)
    monkeypatch.setattr("veramynd_parser.normalize.llm.time.sleep", sleeps.append)
    with pytest.raises(LlmError, match="billing_not_active"):
        structured_complete(
            system="sys", user="usr", schema_model=_Target, model="gpt-x"
        )
    assert calls["n"] == 1
    assert sleeps == []


def test_openai_fails_fast_on_insufficient_quota(monkeypatch):
    sleeps: list[float] = []
    calls = {"n": 0}

    def create(**kwargs):
        calls["n"] += 1
        mod = sys.modules["openai"]
        raise mod.RateLimitError(
            "You exceeded your current quota",
            code="insufficient_quota",
        )

    _install_fake_openai(monkeypatch, create)
    monkeypatch.setattr("veramynd_parser.normalize.llm.time.sleep", sleeps.append)
    with pytest.raises(LlmError, match="insufficient_quota"):
        structured_complete(
            system="sys", user="usr", schema_model=_Target, model="gpt-x"
        )
    assert calls["n"] == 1
    assert sleeps == []


def test_openai_retries_rate_limit_exceeded(monkeypatch):
    sleeps: list[float] = []
    calls = {"n": 0}

    def create(**kwargs):
        calls["n"] += 1
        mod = sys.modules["openai"]
        if calls["n"] == 1:
            raise mod.RateLimitError(
                "Rate limit reached. Please try again in 0.1s",
                code="rate_limit_exceeded",
            )
        return mod._Resp(
            content='{"code": "G1M2U1L1", "student_competencies": [], '
            '"pedagogy_terms": [], "instructional_text": "", "prompt_version": "v1", '
            '"provider": "", "model": ""}'
        )

    _install_fake_openai(monkeypatch, create)
    monkeypatch.setattr("veramynd_parser.normalize.llm.time.sleep", sleeps.append)
    result = structured_complete(
        system="sys", user="usr", schema_model=_Target, model="gpt-x"
    )
    assert result.code == "G1M2U1L1"
    assert calls["n"] == 2
    assert len(sleeps) == 1
    assert sleeps[0] == pytest.approx(1.1)


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


def test_anthropic_api_key_requires_env(monkeypatch):
    from veramynd_parser.normalize.llm import anthropic_api_key

    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setattr("veramynd_parser.normalize.llm.load_dotenv", lambda: None)
    with pytest.raises(LlmError, match="ANTHROPIC_API_KEY"):
        anthropic_api_key(None)


def test_is_non_retryable_anthropic_auth_and_billing():
    from veramynd_parser.normalize.llm import is_non_retryable_anthropic_error

    class E(Exception):
        pass

    auth = E("authentication_error: invalid x-api-key")
    assert is_non_retryable_anthropic_error(auth) is True
    billing = E("Your credit balance is too low to access the Anthropic API")
    assert is_non_retryable_anthropic_error(billing) is True
    rate = E("rate_limit_error: 429")
    rate.status_code = 429
    assert is_non_retryable_anthropic_error(rate) is False


def test_strict_openai_schema_requires_every_property_and_forbids_extras():
    schema = _strict_openai_schema(_Target)
    assert schema["additionalProperties"] is False
    assert set(schema["required"]) == set(_Target.model_fields.keys())
    for prop in schema["properties"].values():
        assert "default" not in prop


def _make_openai_module(create_impl) -> types.ModuleType:
    mod = types.ModuleType("openai")

    class RateLimitError(Exception):
        def __init__(self, message="", *, code=None, body=None, status_code=429):
            super().__init__(message)
            self.code = code
            self.body = body
            self.status_code = status_code

    class APIStatusError(Exception):
        def __init__(self, message="", status_code=500, *, code=None, body=None):
            super().__init__(message)
            self.status_code = status_code
            self.code = code
            self.body = body

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


def _make_anthropic_module(create_impl) -> types.ModuleType:
    mod = types.ModuleType("anthropic")

    class APIStatusError(Exception):
        def __init__(self, message="", *, status_code=500, body=None):
            super().__init__(message)
            self.status_code = status_code
            self.body = body

    class RateLimitError(APIStatusError):
        pass

    class APIConnectionError(Exception):
        pass

    class APITimeoutError(Exception):
        pass

    class _Block:
        def __init__(self, payload: dict):
            self.type = "tool_use"
            self.input = payload

    class _Resp:
        def __init__(self, payload: dict, stop_reason: str = "tool_use"):
            self.stop_reason = stop_reason
            self.content = [_Block(payload)]

    class _Messages:
        def create(self, **kwargs):
            return create_impl(**kwargs)

    class Anthropic:
        def __init__(self, api_key: str | None = None) -> None:
            self.api_key = api_key
            self.messages = _Messages()

    mod.Anthropic = Anthropic
    mod.APIStatusError = APIStatusError
    mod.RateLimitError = RateLimitError
    mod.APIConnectionError = APIConnectionError
    mod.APITimeoutError = APITimeoutError
    mod._Resp = _Resp
    return mod


def _install_fake_anthropic(monkeypatch, create_impl):
    monkeypatch.setitem(sys.modules, "anthropic", _make_anthropic_module(create_impl))
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")


def test_uses_max_completion_tokens_for_gpt5_family():
    assert uses_max_completion_tokens("gpt-5") is True
    assert uses_max_completion_tokens("gpt-5-mini") is True
    assert uses_max_completion_tokens("o1-mini") is True
    assert uses_max_completion_tokens("gpt-4.1") is False
    assert uses_max_completion_tokens("gpt-4.1-mini") is False


def test_build_chat_completion_request_selects_token_param():
    legacy = build_chat_completion_request(
        model="gpt-4.1",
        messages=[{"role": "user", "content": "hi"}],
        max_tokens=2048,
        schema_model=_Target,
    )
    assert "max_tokens" in legacy
    assert "max_completion_tokens" not in legacy
    assert legacy["temperature"] == 0

    modern = build_chat_completion_request(
        model="gpt-5",
        messages=[{"role": "user", "content": "hi"}],
        max_tokens=2048,
        schema_model=_Target,
    )
    assert modern["max_completion_tokens"] == 2048
    assert "max_tokens" not in modern
    assert "temperature" not in modern


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


def test_openai_gpt5_sends_max_completion_tokens(monkeypatch):
    seen: list[dict] = []

    def create(**kwargs):
        seen.append(kwargs)
        mod = sys.modules["openai"]
        return mod._Resp(
            content='{"code": "G1M2U1L1", "student_competencies": [], '
            '"pedagogy_terms": [], "instructional_text": "", "prompt_version": "v1", '
            '"provider": "", "model": ""}'
        )

    _install_fake_openai(monkeypatch, create)
    structured_complete(
        system="sys", user="usr", schema_model=_Target, model="gpt-5", max_tokens=1024
    )
    assert len(seen) == 1
    assert seen[0]["max_completion_tokens"] == 1024
    assert "max_tokens" not in seen[0]


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
    seen_budgets: list[int] = []

    def create(**kwargs):
        seen_budgets.append(_token_budget_from_request(kwargs))
        mod = sys.modules["openai"]
        return mod._Resp(content='{"code": "x"', finish_reason="length")

    _install_fake_openai(monkeypatch, create)
    with pytest.raises(LlmError, match="truncated"):
        structured_complete(
            system="sys", user="usr", schema_model=_Target, model="gpt-x", max_tokens=8
        )
    # Retries must raise the budget, not spin on the same max_tokens.
    assert seen_budgets[0] == 8
    assert seen_budgets[1] > 8
    assert seen_budgets == sorted(seen_budgets)


def test_openai_truncation_succeeds_after_budget_bump(monkeypatch):
    def create(**kwargs):
        mod = sys.modules["openai"]
        if _token_budget_from_request(kwargs) < 100:
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


def _judge_token_key(kwargs: dict) -> str:
    if "max_completion_tokens" in kwargs:
        assert "max_tokens" not in kwargs
        return "max_completion_tokens"
    assert "max_tokens" in kwargs
    return "max_tokens"


def test_judge_modes_use_anthropic_messages_api(tmp_path, monkeypatch):
    """Batch, pair, escalation, and pair-fallback all call Anthropic.messages.create."""
    import json
    from pathlib import Path

    from veramynd_parser.judge.pipeline import judge_retrieve_file

    quote = "Students identify characters and the setting in the story."
    lesson_path = tmp_path / "G1M2U1L3.json"
    lesson_path.write_text(
        json.dumps(
            {
                "code": "G1M2U1L3",
                "title": "Lesson 3",
                "instructional_blocks": [
                    {
                        "section": "Work Time",
                        "letter": "B",
                        "title": "Close Read",
                        "page": 70,
                        "steps": [quote],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    retrieve_path = tmp_path / "retrieve.json"
    retrieve_path.write_text(
        json.dumps({"candidates": [{"standard_code": "1.T.T.1.a", "rrf_score": 0.03}]}),
        encoding="utf-8",
    )
    std_dir = tmp_path / "normalize_standards"
    std_dir.mkdir()
    (std_dir / "1.T.T.1.a.json").write_text(
        json.dumps(
            {
                "standard_code": "1.T.T.1.a",
                "raw_text": "Identify characters and setting.",
                "competency_statement": "Identify story elements.",
                "domain": {"primary": "Comprehension"},
            }
        ),
        encoding="utf-8",
    )

    recorded: list[tuple[str, str]] = []
    mode = {"path": "batch", "fail_batch": False}

    def _pair_payload(*, status: str = "full", confidence: str = "high") -> dict:
        needs_review = confidence in {"low", "medium"}
        return {
            "candidate_id": "G1M2U1L3",
            "location": "page 70",
            "standard_code": "1.T.T.1.a",
            "clauses": [
                {
                    "clause": "identify setting",
                    "judgment": "met" if status != "none" else "not_met",
                    "actor": "student" if status != "none" else "none",
                    "student_quote": quote if status != "none" else "",
                    "teacher_quote": "",
                    "why": "ok" if status != "none" else "",
                }
            ],
            "alignment": status,
            "needs_review": needs_review,
            "review_reason": "partial-or-full" if needs_review else "",
            "evidence": quote if status != "none" else "",
            "anchor_note": "",
        }

    def _batch_payload(*, status: str = "full", confidence: str = "high") -> dict:
        item = _pair_payload(status=status, confidence=confidence)
        return {"results": [item]}

    def create(**kwargs):
        assert "max_tokens" in kwargs
        assert "max_completion_tokens" not in kwargs
        model = kwargs["model"]
        recorded.append((mode["path"], model))
        mod = sys.modules["anthropic"]
        tools = kwargs.get("tools") or []
        schema_name = tools[0]["name"] if tools else ""

        if mode["fail_batch"] and schema_name == "JudgeClientBatchDraft":
            raise mod.APIStatusError("batch boom", status_code=400)

        if schema_name == "JudgeClientBatchDraft":
            if mode["path"] == "escalate":
                return mod._Resp(
                    _batch_payload(status="partial", confidence="medium")
                )
            return mod._Resp(_batch_payload())
        return mod._Resp(_pair_payload())

    _install_fake_anthropic(monkeypatch, create)

    mode["path"] = "batch"
    report = judge_retrieve_file(
        retrieve_file=retrieve_path,
        standards_dir=std_dir,
        lesson_file=lesson_path,
        model="claude-sonnet-4-5",
        escalate=False,
        use_cache=False,
        batch=True,
    )
    assert report["judge_mode"] == "batch"
    assert ("batch", "claude-sonnet-4-5") in recorded

    recorded.clear()
    mode["path"] = "pair"
    report = judge_retrieve_file(
        retrieve_file=retrieve_path,
        standards_dir=std_dir,
        lesson_file=lesson_path,
        model="claude-sonnet-4-5",
        escalate=False,
        use_cache=False,
        batch=False,
    )
    assert report["judge_mode"] == "pair"
    assert ("pair", "claude-sonnet-4-5") in recorded

    recorded.clear()
    mode["path"] = "escalate"
    report = judge_retrieve_file(
        retrieve_file=retrieve_path,
        standards_dir=std_dir,
        lesson_file=lesson_path,
        model="claude-sonnet-4-5",
        escalate_model="claude-opus-4-6",
        escalate=True,
        use_cache=False,
        batch=True,
    )
    assert any(m == "claude-opus-4-6" for _, m in recorded), recorded
    assert any(m == "claude-sonnet-4-5" for _, m in recorded), recorded
    assert any(v.get("escalated") for v in report["verdicts"])

    recorded.clear()
    mode["path"] = "fallback"
    mode["fail_batch"] = True
    report = judge_retrieve_file(
        retrieve_file=retrieve_path,
        standards_dir=std_dir,
        lesson_file=lesson_path,
        model="claude-sonnet-4-5",
        escalate=False,
        use_cache=False,
        batch=True,
        batch_fallback_pair=True,
    )
    assert report["judge_mode"] == "pair"
    assert ("fallback", "claude-sonnet-4-5") in recorded


def test_anthropic_tool_input_parses_json_string_results():
    from veramynd_parser.normalize.llm import _anthropic_tool_input

    class _Block:
        type = "tool_use"
        input = {"results": '[{"standard_code": "1.T.T.1.a"}]'}

    class _Resp:
        content = [_Block()]

    payload = _anthropic_tool_input(_Resp())
    assert payload["results"] == [{"standard_code": "1.T.T.1.a"}]


def test_anthropic_request_marks_system_and_tools_for_prompt_cache():
    from veramynd_parser.normalize.llm import build_anthropic_message_request

    req = build_anthropic_message_request(
        model="claude-sonnet-4-5",
        system="long shared overlay text " * 50,
        user="lesson payload",
        max_tokens=1024,
        schema_model=_Target,
    )
    assert isinstance(req["system"], list)
    assert req["system"][0]["type"] == "text"
    assert req["system"][0]["cache_control"] == {"type": "ephemeral"}
    assert req["tools"][0]["cache_control"] == {"type": "ephemeral"}
    assert req["messages"][0]["content"] == "lesson payload"


def test_anthropic_usage_tracks_cache_hits_and_cheaper_cost():
    from veramynd_parser.normalize.llm import (
        _record_anthropic_usage,
        anthropic_usage_report,
        reset_anthropic_usage,
    )

    class _Usage:
        input_tokens = 200
        output_tokens = 50
        cache_creation_input_tokens = 5000
        cache_read_input_tokens = 5000

    class _Resp:
        usage = _Usage()

    reset_anthropic_usage()
    _record_anthropic_usage(_Resp(), "claude-sonnet-4-5")
    report = anthropic_usage_report()
    assert report["cache_creation_input_tokens"] == 5000
    assert report["cache_read_input_tokens"] == 5000
    # Cache read is billed at 0.1x input; write at 1.25x — cheaper than
    # billing 10k uncached input tokens at full Sonnet rate.
    uncached_equiv = (200 + 5000 + 5000) * 3.0 / 1_000_000 + 50 * 15.0 / 1_000_000
    assert report["estimated_cost_usd"] < uncached_equiv
    reset_anthropic_usage()
