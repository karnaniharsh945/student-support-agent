# Milestone 1 architecture (Assignment 1 baseline)

```mermaid
flowchart LR
  UI[Streamlit chat<br/>demo-student selector] --> ORCH[AgentOrchestrator<br/>bounded loop]
  ORCH --> LLM[LLM provider<br/>Groq / OpenAI-compatible / mock]
  ORCH --> REG[ToolRegistry<br/>validate + execute]
  ORCH --> MEM[MemoryService<br/>deterministic write policy]
  ORCH --> TRC[TraceService]
  REG --> T1[get_fee_status] & T2[get_scholarship_status] & T3[create_support_request] & T4[search_student_policy]
  T1 & T2 & T3 --> SVC[Fee / Scholarship / SupportRequest services]
  T4 --> RET[PolicyRetriever<br/>chunk + TF-IDF vectors]
  SVC & MEM & TRC --> DB[(SQLite)]
```

Agent loop: receive message -> apply memory write policy -> build minimal context (system prompt, relevant memory,
last 6 redacted messages, question) -> model proposes tool call(s) -> registry validates arguments and executes ->
real result fed back -> final answer -> trace persisted (latency, tokens if provided, evidence, memory refs).

Known Milestone-1 limitation (deliberate, fixed in Milestone 2): identity is a *demonstration context* chosen in the
UI, and `get_fee_status` / `get_scholarship_status` accept an optional `student_id`, so a student can ask for another
student's record. The informational probe INFO-01 in the baseline report measures exactly this.
