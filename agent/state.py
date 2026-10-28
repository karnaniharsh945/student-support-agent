"""Shared data structures for the agent loop."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class RequestContext:
    """Who is making this request.

    Built ONLY by AuthService from a validated server-side session (never from chat text, tool
    arguments or frontend fields). `authenticated=False` contexts are refused by the agent.
    """
    session_id: str
    student_id: str | None
    user_id: int | None = None
    username: str = ""
    role: str = "anonymous"            # student | approver | admin | anonymous
    authenticated: bool = False


@dataclass
class ToolResult:
    """Structured result of a tool call. `data` is exactly what the model may see."""
    ok: bool
    data: dict[str, Any] = field(default_factory=dict)
    error_code: str = ""
    user_message: str = ""
    evidence: list[dict[str, Any]] = field(default_factory=list)   # policy chunk metadata
    approval_state: str = ""                                       # e.g. "PENDING" when a sensitive action was queued

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
    permission: str = "n/a"            # allowed | denied | n/a  (authorization outcome for this call)


@dataclass
class AgentResponse:
    reply: str
    run_id: str
    outcome: str                       # answered | tool_error | llm_error | max_steps | clarification ...
    tool_calls: list[ToolCallRecord] = field(default_factory=list)
    evidence: list[dict[str, Any]] = field(default_factory=list)
    memory_refs: list[str] = field(default_factory=list)
    memory_events: list[str] = field(default_factory=list)
    guard_events: list[str] = field(default_factory=list)      # e.g. fabricated citation removed
    latency_ms: float = 0.0
    input_tokens: int | None = None
    output_tokens: int | None = None
    error_category: str = ""
