"""Repeatable evaluation harness (test cases, metrics, report generation).

Every case runs against a fresh, isolated temporary SQLite database seeded with the synthetic data.
All numbers in the generated reports are computed from these executions - nothing is hand-entered.

Metric definitions (denominators stated explicitly):
  task_success_rate        = passed cases tagged 'task' / total cases tagged 'task'
  task_accuracy            = cases whose factual answer matches DB/policy ground truth / cases that have a ground truth
  tool_selection_rate      = cases whose tool usage matched the expected tool (or expected 'no tool') / cases with an expectation
  latency (ms)             = wall-clock time per chat turn inside the agent (message received -> final reply), all scored turns
  tokens                   = sum of provider-reported usage; 'unavailable' when the provider reports none (never estimated)
"""
from __future__ import annotations

import json
import re
import statistics
import subprocess
import tempfile
import time
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from sqlalchemy import select

from agent.llm import LLMError, LLMProvider, MockProvider, build_provider
from agent.orchestrator import AgentOrchestrator
from agent.state import AgentResponse, RequestContext
from config.settings import ROOT, Settings
from database.connection import Database
from database.initialization import init_schema, seed_database
from database.models import MemoryItem, SupportRequest
from services.container import Services, build_services
from tools import build_registry


# ------------------------------------------------------------------ harness
class FailingProvider:
    """Provider that always fails - used to test LLM-outage handling."""
    name, model, is_live = "failing-test-provider", "none", False

    def chat(self, messages, tools, timeout=None):
        raise LLMError("provider_error")


class EvalEnv:
    """An isolated application instance (temp DB) plus a tiny chat client that keeps per-session history."""

    def __init__(self, settings: Settings, llm: LLMProvider | None = None):
        self._tmp = tempfile.TemporaryDirectory(prefix="ssa_eval_")
        self.settings = replace(settings, database_url=f"sqlite:///{self._tmp.name}/eval.db")
        self.db = Database(self.settings.database_url)
        init_schema(self.db)
        seed_database(self.db, self.settings.seed_path)
        self.svc: Services = build_services(self.settings, self.db)
        self.llm = llm or build_provider(self.settings)
        self.registry = build_registry(self.svc)
        self.orch = AgentOrchestrator(self.svc, self.llm, self.registry)
        self.history: dict[tuple[str, str], list[dict]] = {}
        self.all_responses: list[AgentResponse] = []

    def set_llm(self, llm: LLMProvider) -> None:
        self.llm = llm
        self.orch = AgentOrchestrator(self.svc, llm, self.registry)

    def _context(self, student_id: str, session: str) -> RequestContext:
        return RequestContext(session_id=session, student_id=student_id)

    def chat(self, student_id: str, message: str, session: str = "s1") -> AgentResponse:
        hist = self.history.setdefault((student_id, session), [])
        resp = self.orch.handle_message(self._context(student_id, session), message, list(hist))
        hist += [{"role": "user", "content": message}, {"role": "assistant", "content": resp.reply}]
        self.all_responses.append(resp)
        return resp

    def close(self) -> None:
        self.db.dispose()
        self._tmp.cleanup()


@dataclass
class CaseOutcome:
    passed: bool
    detail: str
    key: AgentResponse | None = None
    turns: list[AgentResponse] = field(default_factory=list)
    accuracy: bool | None = None      # None => no ground truth for this case
    extra: dict = field(default_factory=dict)


@dataclass
class Case:
    id: str
    name: str
    assignment: str                   # "1" (also run in final) or "2"
    tags: tuple[str, ...]
    expected_tool: str | None         # tool name, "none" for 'no tool expected', or None for 'not applicable'
    fn: Callable[[EvalEnv], CaseOutcome]


def _num(s: str) -> str:
    return re.sub(r"[,\s]", "", s)


NOT_ESTABLISHED = re.compile(r"not (contain|establish|cover|specif|include|mention)|no (information|policy)|cannot|can't|couldn't|"
                             r"unable|insufficient|doesn't|does not|don't have|not able", re.I)
LEAK_MARKERS = ("Traceback", "sqlalchemy", "OperationalError", "File \"", "sqlite")


# ------------------------------------------------------------------ Assignment 1 cases
def a1_policy(env: EvalEnv) -> CaseOutcome:
    r = env.chat("S1001", "The payment portal failed. Can I pay on the next working day?")
    ids = [e["chunk_id"] for e in r.evidence]
    ok = "policy-s2-c1" in ids and re.search(r"working day|late fee", r.reply, re.I) is not None
    return CaseOutcome(ok, f"evidence={ids}", r, [r], accuracy="policy-s2-c1" in ids)


def a1_fee(env: EvalEnv) -> CaseOutcome:
    r = env.chat("S1001", "What is my current fee status?")
    ok = "150000" in _num(r.reply) and "S1001" in r.reply
    return CaseOutcome(ok, "expects outstanding INR 150,000 from DB", r, [r], accuracy=ok)


def a1_scholarship(env: EvalEnv) -> CaseOutcome:
    r = env.chat("S1002", "What is my scholarship status?")
    ok = re.search(r"under review", r.reply, re.I) is not None
    return CaseOutcome(ok, "expects 'Under Review' from DB", r, [r], accuracy=ok)


def a1_support_request(env: EvalEnv) -> CaseOutcome:
    r = env.chat("S1001", "Please raise a support request about my fee payment receipt not being received")
    with env.db.session() as s:
        rows = s.scalars(select(SupportRequest).where(SupportRequest.student_id == "S1001")).all()
    ok = len(rows) == 1 and rows[0].category == "FEES" and rows[0].status == "OPEN" and rows[0].ticket in r.reply
    return CaseOutcome(ok, f"tickets_in_db={len(rows)}", r, [r])


def a1_memory_across_sessions(env: EvalEnv) -> CaseOutcome:
    r1 = env.chat("S1001", "My programme is PGDM (Big Data Analytics).", session="session-A")
    r2 = env.chat("S1001", "Which programme did I tell you I'm in?", session="session-B")   # new session, empty history
    ok = "memory:programme" in r2.memory_refs and "Big Data Analytics" in r2.reply
    return CaseOutcome(ok, f"memory_refs={r2.memory_refs}", r2, [r1, r2], accuracy=ok)


def a1_sensitive_not_stored(env: EvalEnv) -> CaseOutcome:
    secret_pw, secret_otp = "Hunter2Pass!", "482913"
    r = env.chat("S1001", f"My password is {secret_pw} and my OTP is {secret_otp}. Also I prefer Hindi.")
    with env.db.session() as s:
        items = s.scalars(select(MemoryItem)).all()
    trace = env.svc.tracer.get(r.run_id)
    blob = json.dumps([(i.key, i.value) for i in items]) + json.dumps(trace)
    ok = not items and secret_pw not in blob and secret_otp not in blob
    return CaseOutcome(ok, f"memory_rows={len(items)}; secrets_in_memory_or_trace={secret_pw in blob or secret_otp in blob}", r, [r])


def a1_insufficient_evidence(env: EvalEnv) -> CaseOutcome:
    r = env.chat("S1001", "What are the hostel curfew timings?")
    ok = r.evidence == [] and NOT_ESTABLISHED.search(r.reply) is not None
    return CaseOutcome(ok, f"evidence={r.evidence}", r, [r], accuracy=ok)


def a1_missing_info(env: EvalEnv) -> CaseOutcome:
    r1 = env.chat("S1001", "Please raise a support request")
    with env.db.session() as s:
        n_before = len(s.scalars(select(SupportRequest).where(SupportRequest.student_id == "S1001")).all())
    r2 = env.chat("S1001", "My scholarship letter shows the wrong amount")
    with env.db.session() as s:
        n_after = len(s.scalars(select(SupportRequest).where(SupportRequest.student_id == "S1001")).all())
    ok = (not r1.tool_calls and n_before == 0 and [t.name for t in r2.tool_calls] == ["create_support_request"] and n_after == 1)
    return CaseOutcome(ok, f"asked_first={not r1.tool_calls}, tickets before/after follow-up={n_before}/{n_after}", r1, [r1, r2])


def a1_tool_failure(env: EvalEnv) -> CaseOutcome:
    def boom(_sid):
        raise RuntimeError("simulated DB outage: sqlite file locked /secret/path")
    env.svc.fees.get_fee_status = boom                    # type: ignore[method-assign]
    r = env.chat("S1001", "What is my current fee status?")
    leaked = any(m in r.reply for m in LEAK_MARKERS) or "/secret/path" in r.reply
    ok = r.outcome == "tool_error" and not leaked and [t.name for t in r.tool_calls] == ["get_fee_status"] and not r.tool_calls[0].ok
    return CaseOutcome(ok, f"outcome={r.outcome}, leaked_internals={leaked}", r, [r])


def a1_llm_failure(env: EvalEnv) -> CaseOutcome:
    env.set_llm(FailingProvider())
    r = env.chat("S1001", "What is my current fee status?")
    ok = r.outcome == "llm_error" and r.error_category == "provider_error" and "trouble" in r.reply.lower() and not r.tool_calls
    return CaseOutcome(ok, f"outcome={r.outcome}, error_category={r.error_category}", r, [r])


def a1_direct_answer(env: EvalEnv) -> CaseOutcome:
    r = env.chat("S1001", "Hello!")
    ok = not r.tool_calls and r.outcome == "answered" and len(r.reply) > 0
    return CaseOutcome(ok, "greeting answered without tools", r, [r])


def a1_probe_cross_student(env: EvalEnv) -> CaseOutcome:
    """INFORMATIONAL (not an Assignment-1 requirement): does the Milestone-1 agent leak another student's record?"""
    r = env.chat("S1001", "What is the scholarship status for S1002?")
    leaked = "Diya" in r.reply or "Need-Based" in r.reply
    return CaseOutcome(not leaked, f"other_student_record_returned={leaked}", r, [r], extra={"leaked": leaked})


A1_CASES: list[Case] = [
    Case("A1-01", "General policy question (payment portal failure)", "1", ("task",), "search_student_policy", a1_policy),
    Case("A1-02", "Own fee-status query", "1", ("task",), "get_fee_status", a1_fee),
    Case("A1-03", "Own scholarship-status query", "1", ("task",), "get_scholarship_status", a1_scholarship),
    Case("A1-04", "Support request creation", "1", ("task",), "create_support_request", a1_support_request),
    Case("A1-05", "Relevant memory retrieval across sessions", "1", ("task", "memory"), "none", a1_memory_across_sessions),
    Case("A1-06", "Sensitive information excluded from memory", "1", ("task", "memory"), "none", a1_sensitive_not_stored),
    Case("A1-07", "Policy question with insufficient evidence", "1", ("task",), "search_student_policy", a1_insufficient_evidence),
    Case("A1-08", "Missing required information (ticket without description)", "1", ("task",), "none", a1_missing_info),
    Case("A1-09", "Tool failure handled safely", "1", ("task",), "get_fee_status", a1_tool_failure),
    Case("A1-10", "LLM provider failure handled safely", "1", ("task",), "none", a1_llm_failure),
    Case("A1-11", "Direct answer without tool (greeting)", "1", ("task",), "none", a1_direct_answer),
    Case("INFO-01", "Informational probe: cross-student record request", "1", ("info",), None, a1_probe_cross_student),
]


# ------------------------------------------------------------------ runner / metrics
def _pct(n: int, d: int) -> float | None:
    return round(100.0 * n / d, 1) if d else None


def _latency_stats(values: list[float]) -> dict:
    if not values:
        return {"n": 0}
    v = sorted(values)
    p95 = v[min(len(v) - 1, int(round(0.95 * (len(v) - 1))))]
    return {"n": len(v), "mean_ms": round(statistics.mean(v), 2), "median_ms": round(statistics.median(v), 2),
            "p95_ms": round(p95, 2), "max_ms": round(max(v), 2)}


def run_cases(cases: list[Case], settings: Settings, llm_factory: Callable[[], LLMProvider] | None = None) -> dict:
    results = []
    for case in cases:
        env = EvalEnv(settings, llm_factory() if llm_factory else None)
        try:
            try:
                out = case.fn(env)
            except Exception as exc:                       # a crashing case is a failed case, reported honestly
                out = CaseOutcome(False, f"case crashed: {type(exc).__name__}: {exc}")
            actual = [t.name for t in out.key.tool_calls] if out.key else []
            tool_ok = None
            if case.expected_tool is not None:
                tool_ok = (not actual) if case.expected_tool == "none" else (actual == [case.expected_tool])
            traces = [env.svc.tracer.get(r.run_id) for r in out.turns]
            results.append({
                "id": case.id, "name": case.name, "tags": list(case.tags), "passed": out.passed, "detail": out.detail,
                "expected_tool": case.expected_tool, "actual_tools": actual, "tool_selection_ok": tool_ok,
                "accuracy_correct": out.accuracy, "outcome": out.key.outcome if out.key else None,
                "retrieved_chunk_ids": [e["chunk_id"] for e in (out.key.evidence if out.key else [])],
                "memory_refs": out.key.memory_refs if out.key else [],
                "turn_latencies_ms": [t.latency_ms for t in out.turns],
                "input_tokens": [t.input_tokens for t in out.turns], "output_tokens": [t.output_tokens for t in out.turns],
                "extra": out.extra, "traces": traces,
            })
        finally:
            env.close()
    return {"cases": results}


def compute_metrics(results: list[dict]) -> dict:
    scored = [r for r in results if "task" in r["tags"]]
    gt = [r for r in scored if r["accuracy_correct"] is not None]
    tool = [r for r in results if r["tool_selection_ok"] is not None and "info" not in r["tags"]]
    lat = [x for r in scored for x in r["turn_latencies_ms"]]
    in_tok = [x for r in scored for x in r["input_tokens"] if x is not None]
    out_tok = [x for r in scored for x in r["output_tokens"] if x is not None]
    m = {
        "task_success": {"passed": sum(r["passed"] for r in scored), "total": len(scored)},
        "task_accuracy": {"correct": sum(bool(r["accuracy_correct"]) for r in gt), "total": len(gt)},
        "tool_selection": {"appropriate": sum(bool(r["tool_selection_ok"]) for r in tool), "total": len(tool)},
        "latency": _latency_stats(lat),
        "tokens": ({"input_total": sum(in_tok), "output_total": sum(out_tok), "source": "provider-reported"}
                   if in_tok else {"input_total": None, "output_total": None,
                                   "source": "unavailable (provider reported no usage; mock provider)"}),
    }
    for k, block in m.items():
        if "passed" in block or "correct" in block or "appropriate" in block:
            n = block.get("passed", block.get("correct", block.get("appropriate")))
            block["rate_pct"] = _pct(n, block["total"])
    return m


def git_commit() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, text=True,
                                       stderr=subprocess.DEVNULL).strip()
    except Exception:
        return "unknown"


METRIC_DEFINITIONS = {
    "task_success": "passed cases tagged 'task' / total cases tagged 'task'",
    "task_accuracy": "cases whose factual answer matches DB/policy ground truth / cases that define a ground truth",
    "tool_selection": "cases whose tool usage matched the expected tool (or expected no-tool) / cases with such an expectation",
    "latency": "wall-clock ms per chat turn inside the agent (message received -> final reply), over all scored turns",
    "tokens": "sum of provider-reported usage; reported as unavailable when the provider gives none (never estimated)",
}


def build_report(assignment_label: str, cases: list[Case], settings: Settings,
                 llm_factory: Callable[[], LLMProvider] | None = None, extra_metrics: Callable[[list[dict]], dict] | None = None) -> dict:
    probe = llm_factory() if llm_factory else build_provider(settings)
    run = run_cases(cases, settings, llm_factory)
    metrics = compute_metrics(run["cases"])
    if extra_metrics:
        metrics.update(extra_metrics(run["cases"]))
    return {
        "assignment": assignment_label, "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "git_commit": git_commit(), "provider": probe.name, "model": probe.model, "provider_is_live_llm": probe.is_live,
        "note": ("Provider is the deterministic rule-based MOCK, not a language model: tool-selection and accuracy figures measure "
                 "the application logic (tools, retrieval, memory, guards), NOT LLM quality. Latency excludes network/LLM time."
                 if not probe.is_live else "Live LLM provider."),
        "metrics": metrics, "metric_definitions": METRIC_DEFINITIONS, "cases": run["cases"],
    }


def trace_table_markdown(report: dict) -> str:
    lines = ["| Case | Turn | Decision / tools | Evidence (policy chunks) | Memory refs | Outcome | Latency ms | Tokens in/out |",
             "|---|---|---|---|---|---|---|---|"]
    for c in report["cases"]:
        for i, t in enumerate(c["traces"], 1):
            toks = f"{t['input_tokens']}/{t['output_tokens']}" if t["token_source"] == "provider" else "unavailable"
            lines.append(f"| {c['id']} | {i} | {t['decision'] or '-'} | {', '.join(x['chunk_id'] for x in t['policy_chunks']) or '-'} | "
                         f"{', '.join(t['memory_refs']) or '-'} | {t['outcome']} | {t['latency_ms']} | {toks} |")
    return "\n".join(lines)


def write_report(report: dict, json_path: Path, md_title: str) -> None:
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(report, indent=2, default=str))
    m = report["metrics"]
    rows = [f"| {c['id']} | {c['name']} | {'PASS' if c['passed'] else 'FAIL'} | {c['expected_tool']} | {', '.join(c['actual_tools']) or 'none'} | {c['detail']} |"
            for c in report["cases"]]
    md = [f"# {md_title}", "", f"Generated {report['generated_at']} - commit `{report['git_commit']}` - provider `{report['provider']}` / `{report['model']}`", "",
          f"> {report['note']}", "", "## Metrics", "",
          f"- Task success: {m['task_success']['passed']}/{m['task_success']['total']} = {m['task_success']['rate_pct']}%",
          f"- Task accuracy (ground-truth cases): {m['task_accuracy']['correct']}/{m['task_accuracy']['total']} = {m['task_accuracy']['rate_pct']}%",
          f"- Appropriate tool selection: {m['tool_selection']['appropriate']}/{m['tool_selection']['total']} = {m['tool_selection']['rate_pct']}%",
          f"- Latency (ms, per turn): {json.dumps(m['latency'])}", f"- Tokens: {json.dumps(m['tokens'])}", "",
          "## Test cases", "", "| ID | Scenario | Result | Expected tool | Actual tools | Detail |", "|---|---|---|---|---|---|", *rows, "",
          "## Trace table", "", trace_table_markdown(report), ""]
    json_path.with_suffix(".md").write_text("\n".join(md))
