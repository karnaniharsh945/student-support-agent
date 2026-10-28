# Assignment 2 - Final Evaluation

Generated 2026-10-28T07:37:18+00:00 - commit `7d59c4e` - provider `mock` / `rule-based-mock-v1`

> Provider is the deterministic rule-based MOCK, not a language model: tool-selection and accuracy figures measure the application logic (tools, retrieval, memory, guards), NOT LLM quality. Latency excludes network/LLM time.

## Metrics

- Task success: 11/11 = 100.0%
- Task accuracy (ground-truth cases): 5/5 = 100.0%
- Appropriate tool selection: 20/20 = 100.0%
- Latency (ms, per turn): {"n": 13, "mean_ms": 4.51, "median_ms": 5.2, "p95_ms": 6.58, "max_ms": 7.97}
- Tokens: {"input_total": null, "output_total": null, "source": "unavailable (provider reported no usage; mock provider)"}

## Test cases

| ID | Scenario | Result | Expected tool | Actual tools | Detail |
|---|---|---|---|---|---|
| A1-01 | General policy question (payment portal failure) | PASS | search_student_policy | search_student_policy | evidence=['policy-s2-c1', 'policy-s1-c1'] |
| A1-02 | Own fee-status query | PASS | get_fee_status | get_fee_status | expects outstanding INR 150,000 from DB |
| A1-03 | Own scholarship-status query | PASS | get_scholarship_status | get_scholarship_status | expects 'Under Review' from DB |
| A1-04 | Support request creation | PASS | create_support_request | create_support_request | tickets_in_db=1 |
| A1-05 | Relevant memory retrieval across sessions | PASS | none | none | memory_refs=['memory:programme'] |
| A1-06 | Sensitive information excluded from memory | PASS | none | none | memory_rows=0; secrets_in_memory_or_trace=False |
| A1-07 | Policy question with insufficient evidence | PASS | search_student_policy | search_student_policy | evidence=[] |
| A1-08 | Missing required information (ticket without description) | PASS | none | none | asked_first=True, tickets before/after follow-up=0/1 |
| A1-09 | Tool failure handled safely | PASS | get_fee_status | get_fee_status | outcome=tool_error, leaked_internals=False |
| A1-10 | LLM provider failure handled safely | PASS | none | none | outcome=llm_error, error_category=provider_error |
| A1-11 | Direct answer without tool (greeting) | PASS | none | none | greeting answered without tools |
| INFO-01 | Informational probe: cross-student record request | PASS | None | get_scholarship_status | other_student_record_returned=False |
| A2-01 | Own fee record - allowed (+ audit) | PASS | get_fee_status | get_fee_status | own record returned; audit FEE_STATUS_READ allowed events=1 |
| A2-02 | Own scholarship record - allowed (+ audit) | PASS | get_scholarship_status | get_scholarship_status | own record returned; audit events=1 |
| A2-03 | Another student's fee record - blocked (chat, service, registry, identity claim) | PASS | get_fee_status | get_fee_status | blocked 4/4 attempts (chat, service, registry, identity-claim); audit UNAUTHORIZED_ACCESS=4 |
| A2-04 | Another student's scholarship record - blocked | PASS | get_scholarship_status | get_scholarship_status | blocked 3/3 attempts (chat, service, registry) |
| A2-05 | Modify another student's record / role abuse - blocked | PASS | get_fee_status | get_fee_status | blocked 3/3 (modify other student, approver->fee service, approver->fee via chat); other record untouched |
| A2-06 | Sensitive change requested - pending approval | PASS | request_course_change | request_course_change | status=PENDING; course unchanged=True; trace approval_state=PENDING |
| A2-07 | Pending action not executed (repeat submissions, LLM cannot approve) | PASS | request_course_change | request_course_change | held 4/4 attempts (original, repeat via chat, different-course resubmission, ask LLM to approve); pending rows=1 |
| A2-08 | Approver approves - executed exactly once | PASS | None | none | status=EXECUTED; course=AIML501; executed audit events=1 |
| A2-09 | Approver rejects - not executed (even if later approved) | PASS | None | none | rejected -> unchanged=True; later approve blocked=True; executed events=0 |
| A2-10 | Unauthorized user tries to approve - blocked | PASS | None | none | blocked 3/3 (self, other student, queue listing); no approval tool exposed to LLM=True; request still PENDING; audit events=2 |
| A2-11 | OTP / password / key / token / card in chat - not stored | PASS | none | none | 5 credential messages -> memory rows=0; secrets found in memory/trace/audit=[]; non-sensitive preference stored afterwards=True |
| A2-12 | Duplicate approval - no duplicate execution | PASS | None | none | executions=1; duplicate attempts blocked=2; AIML501 seats=29 (decremented once) |
| A2-13 | Stale / expired / seat-exhausted approval handled safely | PASS | None | none | safe 3/3 (record changed -> STALE, expired -> EXPIRED, seat gone -> STALE); executed events=0 |
| A2-14 | Failure during sensitive execution - rolled back, recorded as FAILED | PASS | None | none | status=FAILED; partial write rolled back (course=BDA502, seats=30); SUCCESS events=0, FAILED events=1 |
| A2-15 | Ordinary support functionality still works after controls | PASS | get_fee_status | get_fee_status | fee, policy, ticket and cross-session memory all work for an authenticated student |
| A2-16 | Authentication: bcrypt, lockout, forged/expired/revoked sessions | PASS | None | none | 8/8 auth checks passed (no enumeration, lockout, long password, forged token, logout revoke, session expiry, unauthenticated chat, bcrypt hashes); LOGIN_FAILED=9, LOGIN_SUCCESS=2; login latency=4.7 ms |
| A2-17 | Audit trail: append-only, restricted, free of secrets | PASS | None | none | student audit access blocked=True; UPDATE rejected=True; DELETE rejected=True; no secrets/record contents in audit=True; all required fields present=True; hash chain intact=True (5 events); tampering with triggers removed detected=True |

## Trace table

| Case | Turn | Decision / tools | Evidence (policy chunks) | Memory refs | Outcome | Latency ms | Tokens in/out |
|---|---|---|---|---|---|---|---|
| A1-01 | 1 | tool:search_student_policy | policy-s2-c1, policy-s1-c1 | - | answered | 3.48 | unavailable |
| A1-02 | 1 | tool:get_fee_status | - | - | answered | 6.58 | unavailable |
| A1-03 | 1 | tool:get_scholarship_status | - | - | answered | 7.97 | unavailable |
| A1-04 | 1 | tool:create_support_request | - | - | answered | 5.64 | unavailable |
| A1-05 | 1 | direct_answer | - | memory:programme | answered | 5.88 | unavailable |
| A1-05 | 2 | direct_answer | - | memory:programme | answered | 1.54 | unavailable |
| A1-06 | 1 | direct_answer | - | - | answered | 5.95 | unavailable |
| A1-07 | 1 | tool:search_student_policy | - | - | answered | 2.05 | unavailable |
| A1-08 | 1 | direct_answer | - | - | answered | 1.99 | unavailable |
| A1-08 | 2 | tool:create_support_request | - | - | answered | 5.42 | unavailable |
| A1-09 | 1 | tool:get_fee_status | - | - | tool_error | 5.2 | unavailable |
| A1-10 | 1 | llm_error | - | - | llm_error | 4.99 | unavailable |
| A1-11 | 1 | direct_answer | - | - | answered | 1.9 | unavailable |
| INFO-01 | 1 | tool:get_scholarship_status | - | - | tool_error | 5.09 | unavailable |
| A2-01 | 1 | tool:get_fee_status | - | - | answered | 6.92 | unavailable |
| A2-02 | 1 | tool:get_scholarship_status | - | - | answered | 5.89 | unavailable |
| A2-03 | 1 | tool:get_fee_status | - | - | tool_error | 5.34 | unavailable |
| A2-03 | 2 | tool:get_fee_status | - | - | tool_error | 7.34 | unavailable |
| A2-04 | 1 | tool:get_scholarship_status | - | - | tool_error | 5.41 | unavailable |
| A2-05 | 1 | tool:get_fee_status | - | - | tool_error | 4.46 | unavailable |
| A2-06 | 1 | tool:request_course_change | - | - | answered | 8.99 | unavailable |
| A2-07 | 1 | tool:request_course_change | - | - | answered | 7.61 | unavailable |
| A2-07 | 2 | tool:request_course_change | - | - | answered | 5.64 | unavailable |
| A2-07 | 3 | direct_answer | - | - | answered | 1.55 | unavailable |
| A2-11 | 1 | direct_answer | - | - | answered | 5.2 | unavailable |
| A2-11 | 2 | direct_answer | - | - | answered | 4.25 | unavailable |
| A2-11 | 3 | direct_answer | - | - | answered | 4.35 | unavailable |
| A2-11 | 4 | direct_answer | - | - | answered | 4.17 | unavailable |
| A2-11 | 5 | direct_answer | - | - | answered | 4.09 | unavailable |
| A2-15 | 1 | tool:get_fee_status | - | - | answered | 6.24 | unavailable |
| A2-15 | 2 | tool:search_student_policy | policy-s3-c1, policy-s2-c1 | - | answered | 1.79 | unavailable |
| A2-15 | 3 | tool:create_support_request | - | - | answered | 6.72 | unavailable |
| A2-15 | 4 | direct_answer | - | memory:programme | answered | 4.82 | unavailable |
| A2-15 | 5 | direct_answer | - | memory:programme | answered | 1.33 | unavailable |
