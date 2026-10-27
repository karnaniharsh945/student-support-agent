"""Structured tracing: one persisted row per agent run, with sensitive fields redacted."""
from __future__ import annotations

import json
import time
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select

from database.connection import Database
from database.models import Trace
from services.privacy import redact, redact_mapping

MAX_QUESTION_CHARS = 300


class TraceBuilder:
    """Accumulates facts about a single run; `finish()` persists them."""

    def __init__(self, tracer: "TraceService", session_id: str, student_id: str | None, question: str,
                 provider: str, model: str):
        self.tracer = tracer
        self.run_id = str(uuid.uuid4())
        self.started = time.perf_counter()
        self.created_at = datetime.now(timezone.utc).replace(tzinfo=None)
        self.session_id, self.student_id = session_id, student_id
        self.question = redact(question)[:MAX_QUESTION_CHARS]
        self.provider, self.model = provider, model
        self.category = ""
        self.decision = ""
        self.tool_calls: list[dict[str, Any]] = []
        self.policy_chunks: list[dict[str, Any]] = []
        self.memory_refs: list[str] = []
        self.context_sources: list[str] = []
        self.model_latency_ms = 0.0
        self.llm_calls = 0
        self.in_tokens: int | None = None
        self.out_tokens: int | None = None
        self.error_category = ""
        self.outcome = ""
        self.extra: dict[str, Any] = {}

    def add_usage(self, in_tok: int | None, out_tok: int | None, latency_ms: float) -> None:
        self.llm_calls += 1
        self.model_latency_ms += latency_ms
        if in_tok is not None:
            self.in_tokens = (self.in_tokens or 0) + in_tok
        if out_tok is not None:
            self.out_tokens = (self.out_tokens or 0) + out_tok

    def finish(self, outcome: str) -> float:
        self.outcome = outcome
        self.latency_ms = round((time.perf_counter() - self.started) * 1000, 2)
        self.tracer._persist(self)
        return self.latency_ms


class TraceService:
    def __init__(self, db: Database):
        self.db = db

    def start(self, session_id: str, student_id: str | None, question: str, provider: str, model: str) -> TraceBuilder:
        return TraceBuilder(self, session_id, student_id, question, provider, model)

    def _persist(self, t: TraceBuilder) -> None:
        with self.db.session() as s:
            s.add(Trace(
                run_id=t.run_id, created_at=t.created_at, session_id=t.session_id, student_id=t.student_id,
                question=t.question, category=t.category, decision=t.decision,
                tool_calls_json=json.dumps(redact_mapping(t.tool_calls)),
                policy_chunks_json=json.dumps(t.policy_chunks), memory_refs_json=json.dumps(t.memory_refs),
                context_sources_json=json.dumps(t.context_sources), latency_ms=t.latency_ms,
                model_latency_ms=round(t.model_latency_ms, 2) if t.llm_calls else None,
                input_tokens=t.in_tokens, output_tokens=t.out_tokens,
                token_source="provider" if t.in_tokens is not None else "unavailable",
                llm_calls=t.llm_calls, provider=t.provider, model=t.model,
                error_category=t.error_category, outcome=t.outcome))

    def get(self, run_id: str) -> dict | None:
        with self.db.session() as s:
            row = s.get(Trace, run_id)
            return self._to_dict(row) if row else None

    def recent(self, limit: int = 50) -> list[dict]:
        with self.db.session() as s:
            rows = s.scalars(select(Trace).order_by(Trace.created_at.desc()).limit(limit)).all()
            return [self._to_dict(r) for r in rows]

    @staticmethod
    def _to_dict(r: Trace) -> dict:
        return {
            "run_id": r.run_id, "created_at": r.created_at.isoformat(timespec="seconds"), "session_id": r.session_id,
            "student_id": r.student_id, "question": r.question, "category": r.category, "decision": r.decision,
            "tool_calls": json.loads(r.tool_calls_json), "policy_chunks": json.loads(r.policy_chunks_json),
            "memory_refs": json.loads(r.memory_refs_json), "context_sources": json.loads(r.context_sources_json),
            "latency_ms": r.latency_ms, "model_latency_ms": r.model_latency_ms, "input_tokens": r.input_tokens,
            "output_tokens": r.output_tokens, "token_source": r.token_source, "llm_calls": r.llm_calls,
            "provider": r.provider, "model": r.model, "error_category": r.error_category, "outcome": r.outcome}
