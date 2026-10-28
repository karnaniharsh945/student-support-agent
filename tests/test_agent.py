import json

import httpx
import pytest

from agent.llm import LLMError, LLMResponse, OpenAICompatibleProvider, ToolCall, build_provider
from agent.orchestrator import MAX_TOOL_CALLS_PER_RUN
from config.settings import ConfigurationError, Settings


class LoopingProvider:
    """Always asks for another tool call - the loop must be bounded."""
    name, model, is_live = "looping", "x", False
    calls = 0

    def chat(self, messages, tools, timeout=None):
        LoopingProvider.calls += 1
        return LLMResponse(content=None, tool_calls=[ToolCall(f"c{self.calls}", "search_student_policy", {"query": "late fee"})])


class ScriptedProvider:
    name, model, is_live = "scripted", "x", False

    def __init__(self, responses): self.responses, self.seen = list(responses), []

    def chat(self, messages, tools, timeout=None):
        self.seen.append(messages)
        return self.responses.pop(0)


def test_agent_uses_real_tool_result(env):
    r = env.chat("S1001", "What is my current fee status?")
    assert [t.name for t in r.tool_calls] == ["get_fee_status"] and "150,000" in r.reply


def test_loop_is_bounded(env):
    LoopingProvider.calls = 0
    env.set_llm(LoopingProvider())
    r = env.chat("S1001", "anything")
    assert r.outcome == "max_steps" and LoopingProvider.calls <= env.settings.max_agent_steps
    assert len(r.tool_calls) <= MAX_TOOL_CALLS_PER_RUN


def test_invalid_model_tool_args_do_not_execute(env):
    env.set_llm(ScriptedProvider([
        LLMResponse(None, [ToolCall("1", "create_support_request", "{not json")]),
        LLMResponse("Could you describe the issue?")]))
    r = env.chat("S1001", "raise a ticket")
    assert r.tool_calls[0].error_code == "invalid_arguments" and r.outcome == "clarification"
    assert env.svc.support.list_for_student(env.ctx("S1001")) == []


def test_empty_model_response_handled(env):
    env.set_llm(ScriptedProvider([LLMResponse("")]))
    r = env.chat("S1001", "hi")
    assert r.outcome == "empty_response" and r.reply


def test_context_is_minimal(env):
    env.svc.memory.upsert("S1001", "contact_preference", "sms")
    env.svc.memory.upsert("S1001", "programme", "PGDM")
    p = ScriptedProvider([LLMResponse("ok")])
    env.set_llm(p)
    env.chat("S1001", "What is the late fee?")
    sent = json.dumps(p.seen[0])
    assert "sms" not in sent and "PGDM" not in sent            # unrelated memory not injected
    assert "Hunter" not in sent and "Diya" not in sent         # no other students' data
    assert "SYNTHETIC" not in sent                             # whole handbook not injected


def test_sensitive_values_never_reach_model(env):
    p = ScriptedProvider([LLMResponse("Please do not share that.")])
    env.set_llm(p)
    env.chat("S1001", "my OTP is 998877")
    assert "998877" not in json.dumps(p.seen[0])


def test_trace_recorded_with_evidence_and_latency(env):
    r = env.chat("S1001", "The payment portal failed. Can I pay on the next working day?")
    t = env.svc.tracer.get(r.run_id)
    assert t["decision"] == "tool:search_student_policy" and t["policy_chunks"][0]["chunk_id"] == "policy-s2-c1"
    assert t["latency_ms"] > 0 and t["provider"] == "mock" and t["token_source"] == "unavailable" and t["input_tokens"] is None


def _transport(handler): return httpx.MockTransport(handler)


def test_openai_provider_parses_tool_calls_and_real_usage():
    def handler(req):
        body = json.loads(req.content)
        assert body["tools"] and "Bearer test-key" == req.headers["authorization"]
        return httpx.Response(200, json={"choices": [{"message": {"content": None, "tool_calls": [
            {"id": "c1", "type": "function", "function": {"name": "get_fee_status", "arguments": "{}"}}]}}],
            "usage": {"prompt_tokens": 123, "completion_tokens": 7}})
    p = OpenAICompatibleProvider("groq", "https://x/v1", "test-key", "some-model", _transport(handler))
    r = p.chat([{"role": "user", "content": "hi"}], [{"type": "function", "function": {"name": "get_fee_status"}}])
    assert r.tool_calls[0].name == "get_fee_status" and (r.input_tokens, r.output_tokens) == (123, 7)


@pytest.mark.parametrize("status,category", [(401, "auth_error"), (429, "rate_limited"), (500, "provider_error")])
def test_openai_provider_error_categories(status, category):
    p = OpenAICompatibleProvider("groq", "https://x/v1", "k", "m", _transport(lambda r: httpx.Response(status, text="secret body")))
    with pytest.raises(LLMError) as e:
        p.chat([], [])
    assert e.value.category == category and "secret" not in str(e.value)


def test_openai_provider_timeout_and_garbage():
    def timeout(_): raise httpx.ReadTimeout("t")
    with pytest.raises(LLMError) as e:
        OpenAICompatibleProvider("g", "https://x/v1", "k", "m", _transport(timeout)).chat([], [])
    assert e.value.category == "timeout"
    with pytest.raises(LLMError) as e:
        OpenAICompatibleProvider("g", "https://x/v1", "k", "m", _transport(lambda r: httpx.Response(200, json={"nope": 1}))).chat([], [])
    assert e.value.category == "invalid_response"


def test_missing_configuration_is_explicit():
    base = Settings.from_env(load_env_file=False)
    from dataclasses import replace
    with pytest.raises(ConfigurationError):
        build_provider(replace(base, model_provider="groq", groq_api_key="", model_name="m"))
    with pytest.raises(ConfigurationError):
        build_provider(replace(base, model_provider="groq", groq_api_key="k", model_name=""))


def test_citation_guard_removes_fabricated_chunk_ids(env):
    env.set_llm(ScriptedProvider([LLMResponse("Per policy-s9-c1 you may pay any time.")]))
    r = env.chat("S1001", "can I pay late?")
    assert "policy-s9-c1" not in r.reply and "unverified citation removed" in r.reply
    assert r.guard_events and "guard:citation_removed" in env.svc.tracer.get(r.run_id)["context_sources"]


def test_citation_guard_keeps_real_citations(env):
    r = env.chat("S1001", "The payment portal failed. Can I pay on the next working day?")
    assert "[policy-s2-c1]" in r.reply and not r.guard_events


def test_unknown_tool_fields_are_rejected_not_ignored(env):
    res, _ = env.registry.execute("get_fee_status", {"student_id": "S1001", "role": "admin"}, env.ctx("S1001"))
    assert res.error_code == "invalid_arguments"
