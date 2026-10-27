# Assignment 1 - Baseline Evaluation

Generated 2026-10-27T07:02:24+00:00 - commit `unknown` - provider `mock` / `rule-based-mock-v1`

> Provider is the deterministic rule-based MOCK, not a language model: tool-selection and accuracy figures measure the application logic (tools, retrieval, memory, guards), NOT LLM quality. Latency excludes network/LLM time.

## Metrics

- Task success: 11/11 = 100.0%
- Task accuracy (ground-truth cases): 5/5 = 100.0%
- Appropriate tool selection: 11/11 = 100.0%
- Latency (ms, per turn): {"n": 13, "mean_ms": 3.04, "median_ms": 2.44, "p95_ms": 5.16, "max_ms": 5.75}
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
| INFO-01 | Informational probe: cross-student record request | FAIL | None | get_scholarship_status | other_student_record_returned=True |

## Trace table

| Case | Turn | Decision / tools | Evidence (policy chunks) | Memory refs | Outcome | Latency ms | Tokens in/out |
|---|---|---|---|---|---|---|---|
| A1-01 | 1 | tool:search_student_policy | policy-s2-c1, policy-s1-c1 | - | answered | 3.64 | unavailable |
| A1-02 | 1 | tool:get_fee_status | - | - | answered | 3.2 | unavailable |
| A1-03 | 1 | tool:get_scholarship_status | - | - | answered | 3.15 | unavailable |
| A1-04 | 1 | tool:create_support_request | - | - | answered | 4.68 | unavailable |
| A1-05 | 1 | direct_answer | - | memory:programme | answered | 5.75 | unavailable |
| A1-05 | 2 | direct_answer | - | memory:programme | answered | 1.31 | unavailable |
| A1-06 | 1 | direct_answer | - | - | answered | 2.0 | unavailable |
| A1-07 | 1 | tool:search_student_policy | - | - | answered | 1.96 | unavailable |
| A1-08 | 1 | direct_answer | - | - | answered | 2.44 | unavailable |
| A1-08 | 2 | tool:create_support_request | - | - | answered | 5.16 | unavailable |
| A1-09 | 1 | tool:get_fee_status | - | - | tool_error | 2.32 | unavailable |
| A1-10 | 1 | llm_error | - | - | llm_error | 1.97 | unavailable |
| A1-11 | 1 | direct_answer | - | - | answered | 1.97 | unavailable |
| INFO-01 | 1 | tool:get_scholarship_status | - | - | answered | 4.09 | unavailable |
