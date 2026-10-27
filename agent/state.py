"""Shared data structures for the agent loop."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class RequestContext:
    """Who is making this request. Built by trusted server-side code, never by the LLM."""
    session_id: str
    student_id: str | None


@dataclass
class ToolResult:
    """Structured result of a tool call. `data` is exactly what the model may see."""
    ok: bool
    data: dict[str, Any] = field(default_factory=dict)
    error_code: str = ""
    user_message: str = ""
    evidence: list[dict[str, Any]] = field(default_factory=list)   # policy chunk metadata

    def to_model_payload(self) -> dict[str, Any]:
        if self.ok:
            return {"ok": True, "data": self.data}
        return {"ok": False, "error_code": self.error_code, "message": self.user_message}


@dataclass
class ToolCallRecord:
    name: str
    arguments: dict[str, Any]
    ok: bool
    error_code: str = ""
    latency_ms: float = 0.0


@dataclass
class AgentResponse:
    reply: str
    run_id: str
    outcome: str                       # answered | tool_error | llm_error | max_steps | clarification ...
    tool_calls: list[ToolCallRecord] = field(default_factory=list)
    evidence: list[dict[str, Any]] = field(default_factory=list)
    memory_refs: list[str] = field(default_factory=list)
    memory_events: list[str] = field(default_factory=list)
    latency_ms: float = 0.0
    input_tokens: int | None = None
    output_tokens: int | None = None
    error_category: str = ""
