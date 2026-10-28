"""LLM provider abstraction.

* OpenAICompatibleProvider - real HTTP calls (Groq preset or any OpenAI-style endpoint).
* MockProvider - deterministic rule-based stand-in used for offline tests. It is NOT an LLM;
  every trace records provider="mock" and token usage is reported as unavailable.
"""
from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from typing import Any, Protocol

import httpx

from config.settings import ConfigurationError, Settings

GROQ_BASE_URL = "https://api.groq.com/openai/v1"


class LLMError(Exception):
    """Provider failure. `category` is safe to show; details are never included."""

    def __init__(self, category: str):
        super().__init__(category)
        self.category = category


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: Any   # dict normally; raw string if the model produced invalid JSON


@dataclass
class LLMResponse:
    content: str | None
    tool_calls: list[ToolCall] = field(default_factory=list)
    input_tokens: int | None = None
    output_tokens: int | None = None
    latency_ms: float = 0.0


class LLMProvider(Protocol):
    name: str
    model: str
    is_live: bool

    def chat(self, messages: list[dict], tools: list[dict], timeout: float | None = None) -> LLMResponse: ...


# --------------------------------------------------------------------------- real provider
class OpenAICompatibleProvider:
    is_live = True

    def __init__(self, name: str, base_url: str, api_key: str, model: str,
                 transport: httpx.BaseTransport | None = None, default_timeout: float = 30.0):
        if not api_key:
            raise ConfigurationError(f"{name}: API key is not configured")
        if not model:
            raise ConfigurationError("MODEL_NAME is not configured")
        self.name, self.model = name, model
        self._url = base_url.rstrip("/") + "/chat/completions"
        self._key = api_key
        self._client = httpx.Client(transport=transport, timeout=default_timeout)
        self._timeout = default_timeout

    def chat(self, messages: list[dict], tools: list[dict], timeout: float | None = None) -> LLMResponse:
        payload: dict[str, Any] = {"model": self.model, "messages": messages, "temperature": 0}
        if tools:
            payload.update(tools=tools, tool_choice="auto")
        started = time.perf_counter()
        try:
            r = self._client.post(self._url, json=payload, headers={"Authorization": f"Bearer {self._key}"},
                                  timeout=timeout or self._timeout)
        except httpx.TimeoutException:
            raise LLMError("timeout") from None
        except httpx.HTTPError:
            raise LLMError("network_error") from None
        latency = (time.perf_counter() - started) * 1000
        if r.status_code in (401, 403):
            raise LLMError("auth_error")
        if r.status_code == 429:
            raise LLMError("rate_limited")
        if r.status_code >= 400:
            raise LLMError("provider_error")
        try:
            body = r.json()
            msg = body["choices"][0]["message"]
        except (ValueError, KeyError, IndexError, TypeError):
            raise LLMError("invalid_response") from None
        calls: list[ToolCall] = []
        for tc in msg.get("tool_calls") or []:
            try:
                fn = tc["function"]
                raw = fn.get("arguments") or "{}"
                try:
                    args: Any = json.loads(raw) if isinstance(raw, str) else raw
                except ValueError:
                    args = raw   # invalid JSON from the model -> registry rejects it as invalid_arguments
                calls.append(ToolCall(tc.get("id") or f"call_{len(calls)}", fn["name"], args))
            except (KeyError, TypeError):
                raise LLMError("invalid_response") from None
        usage = body.get("usage") or {}
        return LLMResponse(content=msg.get("content"), tool_calls=calls,
                           input_tokens=usage.get("prompt_tokens"), output_tokens=usage.get("completion_tokens"),
                           latency_ms=round(latency, 2))


# --------------------------------------------------------------------------- mock provider
_POLICY_MARKERS = re.compile(
    r"late fee|policy|can i pay|portal|failed|failure|refund|working day|how do i|how long|how many|covered|"
    r"escalat|deadline|allowed|eligib|instalment|installment|apply|rules?", re.I)
_FEE_WORDS = re.compile(r"\b(fees?|dues|outstanding|balance|owe|payment status)\b", re.I)
_SCH_WORDS = re.compile(r"\bscholarship\b", re.I)
_PERSONAL = re.compile(r"\b(my|mine|i owe|am i|did i|do i owe|status of)\b|\bstatus\b", re.I)
_TICKET = re.compile(r"\b(raise|create|open|log|file|submit|lodge)\b.*\b(ticket|support request|request|complaint|issue)\b", re.I)
_RECALL = re.compile(r"(which|what)\b.*\b(programme|program|language|contact|name)\b.*\b(i|my|me)\b|"
                     r"what did i (tell|say)|do you remember|how should you (contact|reach)", re.I)
_COURSE_CHANGE = re.compile(r"\b(change|switch|move|transfer|swap)\b.*\b(course|elective|subject)\b", re.I)
_APPROVE_ASK = re.compile(r"\b(approve|accept|execute|authori[sz]e)\b.*\b(request|change|apr-?\d+|it)\b", re.I)
_GREET = re.compile(r"^\s*(hi|hello|hey|thanks|thank you|good (morning|afternoon|evening))\b", re.I)
_OFFTOPIC = re.compile(r"\b(weather|cricket|movie|recipe|stock price|joke|football|lyrics)\b", re.I)


class MockProvider:
    """Deterministic rule-based router + extractive answer composer (offline testing only)."""
    name, model, is_live = "mock", "rule-based-mock-v1", False

    # -- public --------------------------------------------------------------
    def chat(self, messages: list[dict], tools: list[dict], timeout: float | None = None) -> LLMResponse:
        started = time.perf_counter()
        last = messages[-1]
        if last["role"] == "tool":
            content, calls = self._compose(messages), []
        else:
            content, calls = self._route(messages, {t["function"]["name"] for t in tools})
        return LLMResponse(content=content, tool_calls=calls,
                           latency_ms=round((time.perf_counter() - started) * 1000, 3))  # tokens: unavailable

    # -- helpers -------------------------------------------------------------
    @staticmethod
    def _system_text(messages: list[dict], marker: str) -> str:
        return "\n".join(m["content"] for m in messages if m["role"] == "system" and marker in m["content"])

    def _memory(self, messages) -> dict[str, str]:
        txt = self._system_text(messages, "MEMORY_CONTEXT")
        return {k.strip(): v.strip() for k, v in re.findall(r"^- (\w+): (.+)$", txt, re.M)}

    @staticmethod
    def _call(name: str, **args) -> list[ToolCall]:
        return [ToolCall("call_1", name, {k: v for k, v in args.items() if v is not None})]

    def _route(self, messages, tool_names) -> tuple[str | None, list[ToolCall]]:
        user = messages[-1]["content"]
        mem = self._memory(messages)
        sid = re.search(r"\bS\d{4}\b", user, re.I)
        sid_val = sid.group(0).upper() if sid else None
        notes = self._system_text(messages, "MEMORY_NOTE")

        if self._system_text(messages, "SECURITY_NOTICE"):
            return ("For your security, please never share passwords, OTPs, PINs or card details with anyone, "
                    "including me. I have not stored what you sent. How else can I help?"), []
        # follow-up to a previous 'please describe the issue' question
        prev_assistant = next((m["content"] for m in reversed(messages[:-1]) if m["role"] == "assistant" and m.get("content")), "")
        if "describe the issue" in prev_assistant and "create_support_request" in tool_names and not _GREET.search(user):
            return None, self._ticket_call(user + " " + prev_assistant, user)
        if _TICKET.search(user) and "create_support_request" in tool_names:
            m = re.search(r"\b(?:about|regarding|because|that|:)\s+(.{10,})", user, re.I)
            desc = m.group(1).strip() if m else ""
            if len(desc) < 10:
                return ("Happy to raise a support request. Please describe the issue in a sentence or two "
                        "(what happened and what you need)."), []
            return None, self._ticket_call(user, desc)
        if "request_course_change" in tool_names:
            if "which course" in prev_assistant.lower() and not _GREET.search(user) and "?" not in user:
                return None, self._call("request_course_change", new_course=user.strip(" .!")[:60])
            if _APPROVE_ASK.search(user):
                return ("I can't approve or execute requests. Course changes are decided by an authorised approver at the "
                        "Academic Office, and nothing changes until then."), []
            if _COURSE_CHANGE.search(user):
                m = re.search(r"\b(?:(?:course|elective|subject)\s+to|(?:switch|move|transfer|swap)\s+to)\s+(?:the\s+)?(.{2,60}?)\s*(?:[.!?]|\bbecause\b|\bsince\b|$)", user, re.I)
                if not m:
                    return "Which course would you like to switch to? You can give the course code or the name.", []
                why = re.search(r"\b(?:because|since)\s+(.{5,200})", user, re.I)
                return None, self._call("request_course_change", new_course=m.group(1).strip(), reason=why.group(1).strip() if why else None)
        if _RECALL.search(user):
            return self._recall(user, mem), []
        if _FEE_WORDS.search(user) and _PERSONAL.search(user) and not _POLICY_MARKERS.search(user) and "get_fee_status" in tool_names:
            return None, self._call("get_fee_status", student_id=sid_val)
        if _SCH_WORDS.search(user) and _PERSONAL.search(user) and not _POLICY_MARKERS.search(user) and "get_scholarship_status" in tool_names:
            return None, self._call("get_scholarship_status", student_id=sid_val)
        if _GREET.search(user):
            name = mem.get("preferred_name")
            return (f"Hello{' ' + name if name else ''}! I can help with fees, scholarships, course changes, "
                    "policy questions and support requests."), []
        if _OFFTOPIC.search(user):
            return "I can only help with student-support topics such as fees, scholarships, course changes and support requests.", []
        if notes and "?" not in user:
            saved = re.search(r"saved: ([\w, ]+)", notes)
            keys = [k.strip() for k in saved.group(1).split(",")] if saved else []
            if keys:
                return "Noted - I'll remember that (" + ", ".join(k.replace('_', ' ') for k in keys) + ").", []
        if "search_student_policy" in tool_names:
            return None, self._call("search_student_policy", query=user[:300])
        return "I'm not able to help with that request.", []

    def _ticket_call(self, context_text: str, description: str) -> list[ToolCall]:
        t = context_text.lower()
        cat = ("SCHOLARSHIP" if "scholarship" in t else "FEES" if re.search(r"\bfee|payment|portal", t)
               else "COURSE_CHANGE" if "course" in t else "TECHNICAL" if re.search(r"login|portal|app|website", t) else "OTHER")
        prio = "HIGH" if re.search(r"urgent|asap|immediately", t) else "NORMAL"
        return self._call("create_support_request", category=cat, description=description.strip()[:500], priority=prio)

    @staticmethod
    def _recall(user: str, mem: dict[str, str]) -> str:
        wanted = [k for k, words in (("programme", ("programme", "program")), ("preferred_language", ("language",)),
                                     ("contact_preference", ("contact", "reach")), ("preferred_name", ("name",)))
                  if any(w in user.lower() for w in words)]
        found = [(k, mem[k]) for k in wanted if k in mem]
        if found:
            return "From what you told me earlier: " + "; ".join(f"{k.replace('_', ' ')}: {v}" for k, v in found) + "."
        return "I don't have that saved from earlier conversations. Tell me and I'll remember it."

    def _compose(self, messages) -> str:
        tool_msg = messages[-1]
        payload = json.loads(tool_msg["content"])
        name = tool_msg.get("name", "")
        if not payload.get("ok"):
            return f"I couldn't complete that: {payload.get('message', 'an error occurred')}"
        d = payload["data"]
        if name == "get_fee_status":
            return (f"Fee status for {d['student_name']} ({d['student_id']}): {d['status'].replace('_', ' ').title()}. "
                    f"Total fee INR {d['total_fee']:,}, paid INR {d['amount_paid']:,}, outstanding INR {d['outstanding']:,}. "
                    f"Next due date: {d['due_date']}.")
        if name == "get_scholarship_status":
            if d["status"] == "NOT_APPLIED":
                return f"{d['student_name']} ({d['student_id']}) has no scholarship application on record."
            amt = f" Amount: INR {d['amount']:,}." if d["amount"] else ""
            return (f"Scholarship status for {d['student_name']} ({d['student_id']}): {d['scheme']} - "
                    f"{d['status'].replace('_', ' ').title()}.{amt} {d['note']}")
        if name == "create_support_request":
            return (f"I've created support request {d['ticket']} (category {d['category']}, priority {d['priority']}, "
                    f"status {d['status']}). The Student Support Desk responds within 2 working days.")
        if name == "request_course_change":
            if d.get("duplicate"):
                return (f"You already have a pending course-change request {d['display_id']} "
                        f"({d['from_course']} -> {d['to_course']}). It is still waiting for approval; no change has been made.")
            return (f"I've submitted course-change request {d['display_id']}: {d['from_course']} -> {d['to_course']} "
                    f"({d['to_course_name']}). It has NOT been applied. It needs approval by the Academic Office "
                    f"(status: {d['status']}, valid until {d['expires_at']}).")
        if name == "search_student_policy":
            if not d.get("sufficient"):
                return ("The available policy document does not establish an answer to that, so I can't give a reliable one. "
                        "Please contact the Student Support Desk, or I can raise a support request for you.")
            best = d["chunks"][0]
            user_q = next((m["content"] for m in reversed(messages) if m["role"] == "user"), "")
            return f"{self._extract(best['text'], user_q)}\n\nSource: {best['section']} [{best['chunk_id']}]"
        return "Done."

    @staticmethod
    def _extract(text: str, query: str) -> str:
        from services.policy_retrieval import tokenize
        sents = re.split(r"(?<=[.!?])\s+", text.replace("\n", " "))
        q = set(tokenize(query))
        ranked = sorted(range(len(sents)), key=lambda i: (-len(q & set(tokenize(sents[i]))), i))[:2]
        return " ".join(sents[i] for i in sorted(ranked))


def build_provider(settings: Settings, transport: httpx.BaseTransport | None = None) -> LLMProvider:
    p = settings.model_provider
    if p == "mock":
        return MockProvider()
    if p == "groq":
        return OpenAICompatibleProvider("groq", GROQ_BASE_URL, settings.groq_api_key, settings.model_name,
                                        transport, settings.llm_timeout_s)
    if p == "openai_compatible":
        if not settings.openai_compatible_base_url:
            raise ConfigurationError("OPENAI_COMPATIBLE_BASE_URL is not configured")
        return OpenAICompatibleProvider("openai_compatible", settings.openai_compatible_base_url,
                                        settings.openai_compatible_api_key, settings.model_name, transport,
                                        settings.llm_timeout_s)
    raise ConfigurationError(f"Unknown MODEL_PROVIDER: {p!r}")
