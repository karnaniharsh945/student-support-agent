# Requirements checklist (assignment PDFs -> implementation -> tests -> evidence)

"A" = explicit requirement in the assignment PDF. "B" = additional requirement from the project brief. Every row below was
verified by an executed test or evaluation case (not just by reading code).

## Assignment 1
| # | Requirement | Src | Implementation | Tests / evidence |
|---|---|---|---|---|
| 1 | Working agent loop; decide when a tool is needed; use the tool result before answering | A | `agent/orchestrator.py` (bounded loop, real tool results fed back) | `test_agent.py::test_agent_uses_real_tool_result`, `test_loop_is_bounded`; eval A1-02 |
| 2 | >= 2 useful tools | A | `tools/` fees, scholarships, support_requests, policy_search (+ course change in A2) | `test_tools.py`; eval A1-02/03/04/01 |
| 3 | Persistent memory across sessions; temporary/sensitive info not stored | A | `services/memory.py` (deterministic allow-list + `services/privacy.py`) | `test_memory.py`; eval A1-05, A1-06 |
| 4 | Retrieval from one policy document, only relevant chunks | A | `data/student_policy.md`, `services/policy_retrieval.py` | `test_policy_retrieval.py`; eval A1-01, A1-07 |
| 5 | Context selection (question + only needed info) | A | `orchestrator._run` (relevant memory only, last 6 redacted turns, no whole handbook) | `test_agent.py::test_context_is_minimal`, `test_sensitive_values_never_reach_model` |
| 6 | Handle missing info, tool errors, unanswerable questions | A | registry sanitising, clarification outcome, sufficiency check | eval A1-07, A1-08, A1-09, A1-10 |
| 7 | Trace per run: accuracy/success, tools used, latency, tokens, retrieved evidence | A | `services/tracing.py`, `services/evaluation.py` | `reports/assignment_1_baseline.{json,md}` |
| 8 | Demonstration scenarios (fee status, portal failure, new-session fact, sensitive statement, insufficient policy) | A | eval cases A1-02, A1-01, A1-05, A1-06, A1-07 | baseline report |
| 9 | Submission: implementation, sample data/policy, README, evaluation table | A | whole repo, `data/`, `README.md`, `reports/` | - |
| 10 | Agent actually uses tools/data (no fabricated records) | B | tool results come from DB; unsupported -> "policy does not establish" | A1-02/03/07 |
| 11 | Bounded steps, timeouts, structured tool-arg validation | B | `MAX_TOOL_CALLS_PER_RUN`, `max_agent_steps`, deadline, pydantic models | `test_loop_is_bounded`, `test_invalid_*` |
| 12 | Provider abstraction, Groq preferred, model name from config | B | `agent/llm.py`, `config/settings.py` | `test_agent.py` (HTTP transport mocked) - **live Groq call NOT executed in this environment** |

## Assignment 2
| # | Requirement | Src | Implementation | Tests / evidence |
|---|---|---|---|---|
| 13 | Student identity: system knows who is signed in | A | `services/authentication.py` (bcrypt, server-side sessions) | `test_authentication.py`; eval A2-16 |
| 14 | Own record allowed; other student's record blocked (read and modify) | A | `services/authorization.py`, `services/records.py` (queries scoped to `ctx.student_id`) | `test_authorization.py`; eval A2-01..05 |
| 15 | Authorization enforced in code, not only by LLM instruction | A | service layer + registry guard; tested with no LLM/frontend | eval A2-03 (service + registry attempts); mutation check in README |
| 16 | >= 1 sensitive action needs approval before execution | A | `services/approvals.py`, `tools/sensitive_actions.py` | `test_approvals.py`; eval A2-06..09 |
| 17 | Approval rejected -> action must not execute | A | CAS claim + status machine | eval A2-09, `test_reject_never_executes` |
| 18 | Audit record: who, what, allowed/approved?, result | A | `services/audit.py` (append-only, triggers) | `test_audit.py`; eval A2-17; `reports/sample_audit_trace.md` |
| 19 | OTP/password in chat never becomes persistent memory | A | `services/privacy.py`, `memory.py`, redaction before LLM/trace/audit | eval A2-11; `test_memory.py` |
| 20 | Tracing/evaluation from A1 remain functional | A | same harness, A1 cases re-run under auth | `evaluation_comparison.md` |
| 21 | Final evaluation vs Assignment 1 (success, privacy, unsafe-action, latency, tokens, trace/audit) | A | `services/evaluation.py::build_comparison_markdown` | `reports/evaluation_comparison.md` |
| 22 | Submission: updated agent, rules explanation, sample trace/audit, comparison table | A | `docs/privacy_and_approval_rules.md`, `reports/` | - |
| 23 | Two-stage approval, requester != approver, no double execution, expiry/stale, transactional | B | `approvals.py` | eval A2-07..14, `test_approvals.py` (incl. concurrent race) |
| 24 | Approver UI, audit/eval inspection UI, usable without LLM | B | `app.py` (quick lookups need no LLM) | `test_ui_smoke.py` |

## Design decisions where the documents are silent
* Sensitive action = course change (matches the brief's suggestion). Approver/admin are separate seeded accounts.
* Mock provider for offline tests; mock results are labelled and never presented as LLM results.
* Retrieval uses sparse TF-IDF vectors (no model download needed); a dense/Chroma backend is an extension point, **not implemented**.
* Token usage is recorded only when the provider reports it; otherwise `unavailable`.
