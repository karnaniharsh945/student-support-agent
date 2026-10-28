# Assignment 1 baseline vs Assignment 2 final - evaluation comparison

Baseline: commit `74bcad5` (tag `milestone-1-assignment-1`, report generated 2026-10-27T07:02:24+00:00); Final: `7d59c4e` (generated 2026-10-28T07:37:18+00:00). Provider: `mock` / `rule-based-mock-v1`.

> Provider is the deterministic rule-based MOCK, not a language model: tool-selection and accuracy figures measure the application logic (tools, retrieval, memory, guards), NOT LLM quality. Latency excludes network/LLM time.

| Metric | Assignment 1 baseline | Assignment 2 result | Absolute change | Interpretation |
|---|---|---|---|---|
| Task success (11 equivalent A1 cases) | 11/11 = 100.0% | 11/11 = 100.0% | +0.0 pp | Normal tasks still complete after adding auth, authorization, audit. |
| Task accuracy (ground-truth cases) | 5/5 = 100.0% | 5/5 = 100.0% | +0.0 pp | Facts still match DB / policy ground truth. |
| Appropriate tool selection | 11/11 = 100.0% | 11/11 = 100.0% | +0.0 pp | Mock router is deterministic; says nothing about LLM tool-choice quality. |
| Mean latency per turn (ms) | 3.04 | 4.51 | +1.47 ms | Overhead of session validation, permission checks and audit writes (mock model; excludes network/LLM time). |
| p95 latency per turn (ms) | 5.16 | 6.58 | +1.42 ms | Small sample (n=13 / 13 turns). |
| Token usage (input/output) | unavailable (provider reported no usage; mock provider) | unavailable (provider reported no usage; mock provider) | n/a | Mock provider reports no usage; run with a live provider to measure. |
| Cross-student request via chat (same probe INFO-01) | other student's record RETURNED | blocked | n/a | Measured on the Milestone-1 code (tag milestone-1-assignment-1) and on the final code. |
| Unauthorized-access prevention rate | not implemented in A1 | 10/10 = 100.0% | n/a | Baseline probe INFO-01 returned another student's record (0 of 1 blocked); no isolation existed. |
| Approval enforcement rate (held until approval) | not implemented in A1 | 7/7 = 100.0% | n/a | No sensitive-action workflow existed in A1. |
| Rejection enforcement rate | not implemented in A1 | 2/2 = 100.0% | n/a | Rejected requests never executed. |
| Unauthorized approval attempts blocked | not implemented in A1 | 3/3 = 100.0% | n/a | Students/self-approval refused; no approval tool for the LLM. |
| Stale / expired / seat-exhausted safe handling | not implemented in A1 | 3/3 = 100.0% | n/a | Not executed silently. |
| Credential-in-chat memory privacy | A1-06: 1/1 (keyword filter, 1 message) | 5/5 = 100.0% | n/a | A1 had a simpler keyword filter tested with one message; A2 adds key/token/card/ID shapes and whole-message suppression, and checks traces + audit too. |
| Authentication behaviours verified | not implemented in A1 | 8/8 = 100.0% | n/a | bcrypt, lockout, session expiry/revocation, forged tokens. |
| Audit coverage / integrity checks | not implemented in A1 | 19/19 = 100.0% | n/a | Append-only, restricted, secret-free audit trail. |
| All Assignment-2 scenarios passed | n/a | 17/17 = 100.0% | n/a | See test-case table in assignment_2_final.md. |
| Compromised-model red-team attacks blocked | not tested | 15/15 = 100.0% | n/a | Hostile scripted model; see reports/redteam_report.md. New in the final build. |

## Metric definitions (denominators)

- **task_success**: passed cases tagged 'task' / total cases tagged 'task'
- **task_accuracy**: cases whose factual answer matches DB/policy ground truth / cases that define a ground truth
- **tool_selection**: cases whose tool usage matched the expected tool (or expected no-tool) / cases with such an expectation
- **latency**: wall-clock ms per chat turn inside the agent (message received -> final reply), over all scored turns
- **tokens**: sum of provider-reported usage; reported as unavailable when the provider gives none (never estimated)
- **unauthorized_access_prevention**: unauthorized read/modify attempts correctly blocked (no data returned, denial audited) / total such attempts tested
- **approval_enforcement**: sensitive-action attempts correctly held (not executed) until approval / total sensitive-action attempts tested
- **rejection_enforcement**: rejected requests that never executed (immediately and after a later approve attempt) / total checks
- **unauthorized_approval_blocked**: approval attempts by unauthorized actors that were blocked / total such attempts
- **stale_expired_safe**: stale, expired or seat-exhausted approvals that did NOT execute / total such cases
- **memory_privacy**: credential-bearing messages whose secret was found in NO memory row, trace or audit record / credential messages tested
- **authentication_checks**: authentication behaviours verified / authentication behaviours tested
- **audit_coverage**: expected audit events actually found (or integrity properties verified) / expected

## Honest limitations

- Small, synthetic, deterministic test set: it demonstrates that the implemented controls behave as designed; it does **not** establish production security.
- The mock provider is rule-based. Perfect task/tool scores therefore reflect application logic, not LLM quality; rerun with `--provider env` and a live model for LLM-dependent metrics, latency and token usage.
- Latency here is sub-millisecond-to-millisecond local processing time; a live LLM call typically dominates end-to-end latency.
- Metrics that did not exist in Assignment 1 are marked 'not implemented in A1' rather than given a made-up baseline.
- Security cases are not directly comparable to the baseline because the baseline had no authentication/approval/audit to test.
