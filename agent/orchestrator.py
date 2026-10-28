"""Agent orchestration: a bounded loop in which the model proposes and application code disposes.

Per request:
  1 establish context -> 2 apply memory write policy -> 3 select minimal context (relevant memory,
  recent redacted history) -> 4 call model -> 5 validate + execute proposed tools via the registry ->
  6 feed REAL tool results back -> 7 final answer -> 8 persist trace (latency, tokens, evidence).
"""
from __future__ import annotations

import json
import time
from typing import Any

from agent.llm import LLMError, LLMProvider
from agent.prompts import MEMORY_HEADER, SENSITIVE_NOTICE, SYSTEM_PROMPT
from agent.state import AgentResponse, RequestContext, ToolCallRecord
from services.authentication import AuthenticationError
from agent.tool_registry import ToolRegistry
from services.container import Services
from services.privacy import contains_sensitive, redact

MAX_TOOL_CALLS_PER_RUN = 4
HISTORY_TURNS = 6          # messages (not pairs) kept as conversational context

FRIENDLY = {
    "llm_error": "I'm having trouble reaching the language model right now, so I can't process free-text requests at the moment. "
                 "Please try again shortly. The quick lookups in the sidebar still work.",
    "empty_response": "I wasn't able to produce an answer. Could you rephrase your question?",
    "max_steps": "I couldn't complete that request within the allowed number of steps. Please try a simpler request.",
    "timeout": "That took too long and was stopped. Please try again.",
    "internal_error": "Something went wrong on my side. Please try again, or raise a support request.",
}


class AgentOrchestrator:
    def __init__(self, svc: Services, llm: LLMProvider, registry: ToolRegistry):
        self.svc, self.llm, self.registry = svc, llm, registry

    # ------------------------------------------------------------------ public
    def handle_authenticated(self, session_token: str | None, message: str, history: list[dict] | None = None) -> AgentResponse:
        """Entry point for the UI: identity is derived HERE from the server-side session, never from the caller."""
        try:
            ctx = self.svc.auth.context_from_token(session_token)
        except AuthenticationError as e:
            return AgentResponse(reply=e.message, run_id="", outcome="unauthenticated", error_category=e.reason)
        return self.handle_message(ctx, message, history)

    def handle_message(self, ctx: RequestContext, message: str, history: list[dict] | None = None) -> AgentResponse:
        if not ctx.authenticated:
            return AgentResponse(reply="Please sign in to use the Student Support Agent.", run_id="",
                                 outcome="unauthenticated", error_category="not_authenticated")
        tb = self.svc.tracer.start(ctx.session_id, ctx.student_id, message, self.llm.name, self.llm.model,
                                   user_id=ctx.user_id, role=ctx.role)
        resp_kwargs: dict[str, Any] = {}
        try:
            reply, outcome, tool_recs, evidence, mem_refs, mem_events = self._run(ctx, message, history or [], tb)
        except LLMError as e:
            tb.error_category, tb.decision = e.category, "llm_error"
            self.svc.audit.record("LLM_FAILURE", ctx=ctx, result="failure", error_category=e.category)
            reply, outcome, tool_recs, evidence, mem_refs, mem_events = FRIENDLY["llm_error"], "llm_error", [], [], [], []
        except Exception:
            tb.error_category, tb.decision = "internal_error", "internal_error"
            reply, outcome, tool_recs, evidence, mem_refs, mem_events = FRIENDLY["internal_error"], "internal_error", [], [], [], []
        latency = tb.finish(outcome)
        return AgentResponse(reply=reply, run_id=tb.run_id, outcome=outcome, tool_calls=tool_recs, evidence=evidence,
                             memory_refs=mem_refs, memory_events=mem_events, latency_ms=latency,
                             input_tokens=tb.in_tokens, output_tokens=tb.out_tokens, error_category=tb.error_category,
                             **resp_kwargs)

    # ------------------------------------------------------------------ internals
    def _run(self, ctx, message, history, tb):
        deadline = time.perf_counter() + self.svc.settings.agent_deadline_s
        sensitive = contains_sensitive(message)
        safe_message = redact(message)                         # the model never sees credential values
        tb.context_sources.append("current_question")

        # memory write policy (deterministic) - only for students with a record
        mem_events: list[str] = []
        if ctx.student_id:
            wr = self.svc.memory.remember_from_message(ctx.student_id, message, ctx.session_id)
            if wr.stored:
                mem_events.append("saved: " + ", ".join(wr.stored))
            if wr.blocked_reason:
                mem_events.append(f"not stored ({wr.blocked_reason})")
        if sensitive:
            self.svc.audit.record("SENSITIVE_INPUT_NOT_STORED", ctx=ctx, result="not_stored",
                                  detail={"reason": "credential-like content redacted; not persisted"})

        messages: list[dict[str, Any]] = [{"role": "system", "content": SYSTEM_PROMPT}]
        tb.context_sources.append("system_prompt")
        mem_refs: list[str] = []
        if ctx.student_id:
            items = self.svc.memory.get_relevant(ctx.student_id, safe_message)
            if items:
                mem_refs = [f"memory:{i.key}" for i in items]
                messages.append({"role": "system", "content": MEMORY_HEADER + "\n" + "\n".join(f"- {i.key}: {i.value}" for i in items)})
                tb.context_sources += mem_refs
        saved = [e for e in mem_events if e.startswith("saved")]
        if saved:
            messages.append({"role": "system", "content": "MEMORY_NOTE: " + saved[0]})
        if sensitive:
            messages.append({"role": "system", "content": SENSITIVE_NOTICE})
        recent = [{"role": h["role"], "content": redact(h["content"])} for h in history[-HISTORY_TURNS:]
                  if h.get("role") in ("user", "assistant") and h.get("content")]
        if recent:
            tb.context_sources.append(f"history:{len(recent)}_messages")
        messages += recent
        messages.append({"role": "user", "content": safe_message})
        tb.memory_refs = mem_refs

        tools = self.registry.schemas()
        tool_recs: list[ToolCallRecord] = []
        evidence: list[dict] = []
        total_calls = 0
        final: str | None = None
        for _ in range(self.svc.settings.max_agent_steps):
            if time.perf_counter() > deadline:
                tb.error_category = "timeout"
                return FRIENDLY["timeout"], "timeout", tool_recs, evidence, mem_refs, mem_events
            resp = self.llm.chat(messages, tools, timeout=self.svc.settings.llm_timeout_s)
            tb.add_usage(resp.input_tokens, resp.output_tokens, resp.latency_ms)
            if not resp.tool_calls:
                final = (resp.content or "").strip()
                break
            if total_calls + len(resp.tool_calls) > MAX_TOOL_CALLS_PER_RUN:
                tb.error_category = "tool_loop_limit"
                return FRIENDLY["max_steps"], "max_steps", tool_recs, evidence, mem_refs, mem_events
            messages.append({"role": "assistant", "content": resp.content,
                             "tool_calls": [{"id": c.id, "type": "function",
                                             "function": {"name": c.name, "arguments": json.dumps(c.arguments) if not isinstance(c.arguments, str) else c.arguments}}
                                            for c in resp.tool_calls]})
            for call in resp.tool_calls:
                total_calls += 1
                result, rec = self.registry.execute(call.name, call.arguments, ctx)
                tool_recs.append(rec)
                tb.authorizations.append({"tool": rec.name, "permission": rec.permission})
                if result.approval_state:
                    tb.approval_state = result.approval_state
                tb.tool_calls.append({"name": rec.name, "arguments": rec.arguments, "ok": rec.ok,
                                      "error_code": rec.error_code, "latency_ms": rec.latency_ms})
                tb.context_sources.append(f"tool:{call.name}")
                if result.evidence:
                    evidence += result.evidence
                    tb.policy_chunks += result.evidence
                    tb.context_sources += [f"policy:{e['chunk_id']}" for e in result.evidence]
                messages.append({"role": "tool", "tool_call_id": call.id, "name": call.name,
                                 "content": json.dumps(result.to_model_payload())})
        else:
            tb.error_category = "max_steps"
            return FRIENDLY["max_steps"], "max_steps", tool_recs, evidence, mem_refs, mem_events

        tb.category = tool_recs[0].name if tool_recs else ("memory" if mem_refs else "direct_answer")
        tb.decision = ("tool:" + ",".join(r.name for r in tool_recs)) if tool_recs else "direct_answer"
        if not final:
            tb.error_category = "empty_response"
            return FRIENDLY["empty_response"], "empty_response", tool_recs, evidence, mem_refs, mem_events
        outcome = "answered"
        if tool_recs and not tool_recs[-1].ok:
            tb.error_category = tool_recs[-1].error_code
            outcome = "clarification" if tool_recs[-1].error_code in ("missing_student", "invalid_arguments") else "tool_error"
        return final, outcome, tool_recs, evidence, mem_refs, mem_events
